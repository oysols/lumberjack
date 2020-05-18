import json
import gzip
from typing import List, Dict, Any, Tuple
import logging
import time
import threading

import psycopg2  # type: ignore
import psycopg2.extras  # type: ignore
from psycopg2._psycopg import connection as Conn  # type: ignore
import flask

import jsonlogger


POSTGRES_ARGS = {"host": "timescale", "database": "postgres", "user": "postgres", "password": "pass"}
LOG_RETENTION = "31 days"


app = flask.Flask(__name__)


def insert_bulk(conn: Conn, logs: List[Dict[str, Any]]) -> None:
    with conn:
        with conn.cursor() as c:
            values = ((log["timestamp"], log["raw_log"], log["stream"], json.dumps(log["log"]), json.dumps(log["metadata"])) for log in logs)
            psycopg2.extras.execute_batch(
                c,
                """
                INSERT INTO logs (timestamp, raw_log, stream, log, metadata)
                VALUES (%s, %s, %s, %s, %s)
                """,
                values,
                page_size=1000
            )


@app.route('/bulk', methods=['POST'])
def bulk() -> Tuple[str, int]:
    conn = psycopg2.connect(**POSTGRES_ARGS)
    data = gzip.decompress(flask.request.data)
    logs = json.loads(data)
    insert_bulk(conn, logs)
    return "Success", 200


# TODO: Have dispatchers read latest timestamp from server
# How to do the docker timestamp (-> postgres timestamptz -> python datetime ->) docker timestamp comparison?
# @app.route('/latest_timestamp/<container_id>', methods=['GET'])
# def latest_timestamp(container_id) -> None:
#     conn = psycopg2.connect(host=POSTGRES_HOST, database="postgres", user="postgres", password="pass")
#     with conn:
#         with conn.cursor() as c:
#             c.execute(
#                 """
#                     SELECT timestamp
#                     FROM logs
#                     WHERE metadata ->> 'container_id' = %s
#                     ORDER BY timestamp DESC
#                     LIMIT 1
#                 """,
#                 (container_id, )
#             )
#             c.fetchone()


def drop_chunks():
    with psycopg2.connect(**POSTGRES_ARGS) as conn:
        with conn.cursor() as c:
            c.execute(
                f"""
                SELECT drop_chunks(
                            table_name => 'logs',
                            older_than => interval '{LOG_RETENTION}',
                            cascade_to_materializations => true
                       )
                """
            )


def background_chunk_dropper():
    time.sleep(10)
    while True:
        try:
            logging.info(f"Dropping chunks older than '{LOG_RETENTION}'")
            drop_chunks()
        except Exception:
            logging.exception("Failed to drop chunks")
        time.sleep(60 * 60)


if __name__ == '__main__':
    jsonlogger.setup_json_logger(logging.INFO)
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.WARNING)

    threading.Thread(target=background_chunk_dropper, daemon=True).start()

    app.run(host="0.0.0.0", port="5000", threaded=True)
