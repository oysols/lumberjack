from typing import Dict, Any, List
import threading
import queue
import subprocess
import json
from pathlib import Path
import socket
import sqlite3
import time
import gzip
import argparse
import os

import requests


def get_pod_info_from_kubernetes() -> Dict:
    # Retrieve service account details
    service_account_path = Path("/var/run/secrets/kubernetes.io/serviceaccount")
    if not service_account_path.is_dir():
        raise Exception("Could not access k8s service account credentials")
    bearer_token = (service_account_path / "token").read_text().strip()
    ca_path = service_account_path / "ca.crt"

    service_host = os.environ['KUBERNETES_SERVICE_HOST']
    service_port = os.environ['KUBERNETES_SERVICE_PORT']
    endpoint = "/api/v1/pods"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    res = requests.get(f"https://{service_host}:{service_port}{endpoint}", headers=headers, verify=ca_path)
    pod_info: Dict = res.json()
    return pod_info


def get_k8s_container_meta_data(requested_container_id: str) -> Dict:
    pod_info = get_pod_info_from_kubernetes()
    for pod in pod_info["items"]:
        # pod_labels = pod["metadata"].get("labels", {})
        for container in pod["status"].get("containerStatuses", []):
            container_id = container["containerID"].split("//")[-1]
            if container_id == requested_container_id:
                return {
                    "container_id": container_id,
                    "container_name": container["name"],
                    "container_image": container["image"],
                    "namespace": pod["metadata"]["namespace"],
                    "pod_name": pod["metadata"]["name"],
                    "pod_ip": pod["status"]["podIP"],
                    "host_ip": pod["status"]["hostIP"],
                }
    raise Exception("Container not found in pod info")


def get_docker_inspect(container_id: str) -> Dict:
    out = subprocess.check_output(["docker", "inspect", container_id]).decode()
    data = json.loads(out)
    assert len(data) == 1
    container_info: Dict = data[0]
    return container_info


def get_dockerd_container_meta_data(container_id: str) -> Dict:
    inspect = get_docker_inspect(container_id)
    return {
        "container_id": inspect["Id"],
        "container_name": inspect["Name"],
        "container_image": inspect["Config"]["Image"],
        "container_hostname": inspect["Config"]["Hostname"],
        "host_hostname": socket.gethostname(),
    }


def tail_container_to_queue(container_id: str, log_path: Path, log_queue: queue.Queue, start_line: int = 0) -> None:
    assert start_line > 0
    p = subprocess.Popen(["tail", "--follow=name", str(log_path), "-n", "+{}".format(start_line)], stdout=subprocess.PIPE)
    try:
        if USE_KUBERNETES_SERVICEACCOUNT:
            container_metadata = get_k8s_container_meta_data(container_id)
        else:
            container_metadata = get_dockerd_container_meta_data(container_id)

        line_no = start_line
        while True:
            line = p.stdout.readline()
            if line == b"":
                break

            # Parse
            # Docker logs sometimes include a null byte character. Postgres does not like this, so remove
            line = line.replace(b"\u0000", b"")
            try:
                log_data = json.loads(line.decode())
                raw_log = log_data["log"].strip()  # Strip trailing newlines
                stream = log_data["stream"]
                timestamp = log_data["time"]
            except Exception:
                print("Error: Could not read log line {}:{} '{}'".format(log_path, line_no, line))
                raise
            try:
                parsed_log = json.loads(raw_log)
            except Exception:
                # log line could not be parsed as json
                parsed_log = {}
            log_dict = {
                "line_no": line_no,
                "timestamp": timestamp,  # Convert to unix timestamp?
                "raw_log": raw_log,  # remove if parse success?
                "stream": stream,
                "log": parsed_log,
                "metadata": container_metadata,
            }

            log_queue.put(log_dict)
            line_no += 1
    finally:
        p.kill()
        p.wait()


def get_next_line_no(conn: sqlite3.Connection, container_id: str) -> int:
    with conn as c:
        result = c.execute("SELECT line_no FROM containers WHERE id=?", (container_id, )).fetchone()
        if not result:
            return 1
        else:
            return int(result[0]) + 1


def scan_and_tail_logs_in_threads(conn: sqlite3.Connection, log_tail_threads: Dict[str, threading.Thread], log_queue: queue.Queue) -> None:
    for container in LOG_DIR.iterdir():
        container_id = container.name
        if log_tail_threads.get(container_id):
            continue
        log = container / "{}-json.log".format(container_id)
        if log.is_file():
            line_no = get_next_line_no(conn, container_id)
            thread = threading.Thread(target=tail_container_to_queue, args=(container_id, log.absolute(), log_queue, line_no), daemon=True)
            thread.start()
            log_tail_threads[container_id] = thread


def set_line_no_state(cursor: sqlite3.Cursor, container_id: str, line_no: int) -> None:
    cursor.execute("INSERT OR REPLACE INTO containers VALUES (?, ?)", (container_id, line_no))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Collect docker logs and send them to logging server')
    parser.add_argument('--kubernetes', help='Use kubernetes service account to collect metadata', action="store_true")
    args = parser.parse_args()

    USE_KUBERNETES_SERVICEACCOUNT = args.kubernetes

    LOGGER_SERVER_HOST = "http://lumberjack-server:5000"

    LOG_DIR = Path("/var/lib/docker/containers/")

    # Local DB for storing which logs have been submitted
    LOCAL_STATE_DB_PATH = LOG_DIR / "lumberjack-state.db"
    conn = sqlite3.connect(str(LOCAL_STATE_DB_PATH))
    conn.execute("CREATE TABLE IF NOT EXISTS containers (id VARCHAR UNIQUE, line_no VARCHAR)")

    log_queue = queue.Queue(maxsize=2000)  # type: queue.Queue[Dict[str, Any]]
    max_logs_per_post = 1000
    post_interval = 5
    scan_interval = 10
    sleep_duration = 0.5
    backoff_duration = 5

    log_tail_threads: Dict[str, threading.Thread] = {}
    last_scan_time = time.time()
    last_send_time = time.time()
    should_sleep = False

    while True:
        if time.time() - last_scan_time > scan_interval:
            scan_and_tail_logs_in_threads(conn, log_tail_threads, log_queue)
            last_scan_time = time.time()

        if not should_sleep or time.time() - last_send_time > post_interval:
            with conn as cursor:
                updated_line_nos = {}
                logs: List[Dict[str, Any]] = []
                while len(logs) < max_logs_per_post:
                    # Fetch new logs from queue
                    try:
                        log_dict = log_queue.get_nowait()
                    except queue.Empty:
                        break
                    updated_line_nos[log_dict["metadata"]["container_id"]] = log_dict["line_no"]
                    logs.append(log_dict)

                if logs:
                    # Keep track of submitted log lines
                    for container_id, line_no in updated_line_nos.items():
                        set_line_no_state(cursor, container_id, line_no)

                    # Send log lines to server
                    headers = {'Content-Encoding': 'gzip'}
                    data = gzip.compress(json.dumps(logs).encode())
                    resp = requests.post("{}/bulk".format(LOGGER_SERVER_HOST), data=data, headers=headers)
                    if resp.status_code != 200:
                        print(f"Error: Failed to post logs to server. Status code {resp.status_code}")
                        time.sleep(backoff_duration)
                        raise

                    # Reset timer
                    last_send_time = time.time()

                if len(logs) == max_logs_per_post:
                    should_sleep = False
                else:
                    should_sleep = True

        # Sleep if nothing was done
        if should_sleep:
            time.sleep(sleep_duration)
