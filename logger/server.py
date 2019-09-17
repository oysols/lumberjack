from datetime import datetime
import json
import time

import psycopg2
import psycopg2.extras
import flask


app = flask.Flask(__name__)


POSTGRES_HOST = "timescale"


def insert_bulk(conn, logs):
    with conn:
        with conn.cursor() as c:
            start = time.time()
            values = ((log["timestamp"], log["docker"]["container_id"], json.dumps(log)) for log in logs)
            print("parse values", time.time() - start)
            start = time.time()
            psycopg2.extras.execute_batch(
                c,
                """
                INSERT INTO logs (time, meta, data)
                VALUES (%s, %s, %s)
                """,
                values,
                page_size=1000
            )
            print("perform query", time.time() - start)

import gzip
import json
@app.route('/bulk', methods=['POST'])
def bulk():
    start = time.time()
    conn = psycopg2.connect(host=POSTGRES_HOST, database="postgres", user="postgres", password="pass")
    data = gzip.decompress(flask.request.data)
    logs = json.loads(data)
    print("prepare", time.time() - start)
    try:
        insert_bulk(conn, logs)
    except:
        print(logs)
        raise
    return "Success", 200


def select_all():
    """
    SELECT DISTINCT data -> 'docker' -> 'container_name' FROM logs;
    SELECT data -> 'raw_log' FROM logs WHERE data -> 'docker' ->> 'container_name' LIKE '%cherry%' AND data->> 'raw_log' LIKE '%/job%';
    SELECT time_bucket('1 hour', time) bucket, count(*) FROM logs GROUP BY bucket ORDER BY bucket;
    """
    with conn:
        with conn.cursor() as c:
            c.execute("SELECT * from logs")
            for line in c.fetchall():
                print(line)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port="5000", threaded=True)
