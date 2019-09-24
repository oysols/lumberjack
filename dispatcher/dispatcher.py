import threading
import queue
import subprocess
import json
from pathlib import Path
import socket
import sqlite3
import time
import gzip

import requests


def docker_inspect(container):
    out = subprocess.check_output(["docker", "inspect", container]).decode()
    data = json.loads(out)
    assert len(data) == 1
    return data[0]


def tail_container_to_queue(container_id, log_path, log_queue, start_line=0):
    assert start_line > 0
    p = subprocess.Popen(["tail", "-f", str(log_path), "-n", "+{}".format(start_line)], stdout=subprocess.PIPE)
    try:
        inspect = docker_inspect(container_id)

        # TODO: Remove
        #if "logger-" in inspect["Name"]:
        #    return

        docker_info = {
                "container_id": inspect["Id"],
                "container_name": inspect["Name"],
                "conatiner_image": inspect["Config"]["Image"],
                "container_hostname": inspect["Config"]["Hostname"],
                "host_hostname": socket.gethostname(),
        }

        line_no = start_line
        while True:
            line = p.stdout.readline()
            if line == b"":
                break

            # Parse
            line = line.replace(b"\u0000", b"")
            try:
                log_data = json.loads(line.decode())
                raw_log = log_data["log"]
                stream = log_data["stream"]
                timestamp = log_data["time"]
                parsed_log = None
            except Exception:
                print("Error: Could not read log line {}:{} '{}'".format(log_path, line_no, line))
                raise
            try:
                parsed_log = json.loads(raw_log)
            except:
                pass
            log_dict = {
                "line_no": line_no,
                "raw_log": raw_log,  # remove if parse success?
                "log": parsed_log,
                "timestamp": timestamp,
                "stream": stream,
                "docker": docker_info,
            }

            log_queue.put(log_dict)
            line_no += 1
    finally:
        p.kill()


def scan_and_tail_logs_in_threads(conn, log_tail_threads, log_queue):
    for container in LOG_DIR.iterdir():
        if log_tail_threads.get(container):
            continue
        log = container / "{}-json.log".format(container.name)
        if log.is_file():
            line_no = get_next_line_no(conn, container.name)
            thread = threading.Thread(target=tail_container_to_queue, args=(container.name, log.absolute(), log_queue, line_no), daemon=True)
            thread.start()
            log_tail_threads[container] = thread


def get_next_line_no(conn, container):
    with conn as c:
        result = c.execute("SELECT line_no FROM containers WHERE id=?", (container, )).fetchone()
        if not result:
            return 1
        else:
            return int(result[0]) + 1


def set_line_no_state(cursor, container, line_no):
    cursor.execute("INSERT OR REPLACE INTO containers VALUES (?, ?)", (container, line_no))


if __name__ == "__main__":
    LOGGER_SERVER_HOST = "http://logger-server:5000"

    LOG_DIR = Path("/var/lib/docker/containers/")

    # Local DB for storing which logs have been submitted
    LOCAL_STATE_DB_PATH = LOG_DIR / "lumberjack-state.db"
    conn = sqlite3.connect(str(LOCAL_STATE_DB_PATH))
    conn.execute("CREATE TABLE IF NOT EXISTS containers (id VARCHAR UNIQUE, line_no VARCHAR)")

    log_queue = queue.Queue(maxsize=2000)
    max_logs_per_post = 1000
    post_interval = 5
    scan_interval = 10
    sleep_duration = 0.5
    backoff_duration = 5

    log_tail_threads = {}
    last_scan_time = time.time()
    last_send_time = time.time()
    should_sleep = False

    while True:
        if time.time() - last_scan_time > scan_interval:
            scan_and_tail_logs_in_threads(conn, log_tail_threads, log_queue)
            last_scan_time = time.time()

        if not should_sleep or time.time() - last_send_time > post_interval:
            start = time.time()
            with conn as cursor:
                updated_line_nos = {}
                logs = []
                while len(logs) < max_logs_per_post:
                    # Fetch new logs from queue
                    try:
                        log_dict = log_queue.get_nowait()
                    except queue.Empty:
                        break
                    updated_line_nos[log_dict["docker"]["container_id"]] = log_dict["line_no"]
                    logs.append(log_dict)

                if logs:
                    # Keep track of submitted log lines
                    for container_id, line_no in updated_line_nos.items():
                        set_line_no_state(cursor, container_id, line_no)
                    print(f"Parsed {len(logs)} logs in {time.time() - start}")
                    start = time.time()

                    # Send log lines to remote DB
                    headers = {'Content-Encoding': 'gzip'}
                    data = gzip.compress(json.dumps(logs).encode())
                    print("Sending:", len(json.dumps(logs)), "bytes Compressed", len(data))
                    resp = requests.post("{}/bulk".format(LOGGER_SERVER_HOST), data=data, headers=headers)
                    try:
                        resp.raise_for_status()
                    except Exception as e:
                        time.sleep(backoff_duration)
                        raise
                    print("Sent in", time.time() - start)

                    # Reset timer
                    last_send_time = time.time()

                if len(logs) == max_logs_per_post:
                    should_sleep = False
                else:
                    should_sleep = True

        # Sleep if nothing was done
        if should_sleep:
            time.sleep(sleep_duration)
