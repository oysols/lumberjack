from datetime import datetime
import json
import time

import psycopg2
import flask


app = flask.Flask(__name__)


def insert_bulk(logs):
    with conn:
        with conn.cursor() as c:
            c.executemany("""
                INSERT INTO logs (time, meta, data)
                VALUES (%s, %s, %s)
                """,
                [(log["timestamp"], log["docker"]["container_id"], json.dumps(log)) for log in logs],
            )


@app.route('/bulk', methods=['POST'])
def bulk():
    conn = psycopg2.connect(host="localhost", database="postgres", user="postgres", password="pass")
    logs = flask.request.json
    try:
        insert_bulk(logs)
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
