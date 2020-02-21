# Lumberjack

Log aggregation and storage of docker container logs from kubernetes or single docker host.

## Dispatcher

- Runs an instance on all nodes in cluster
- Fetches logs from local containers by using `tail -f`
- POSTs logs in bulk to the server
- Keeps track of which logs have been sent

## Server

- Single instance
- Receives logs from dispatchers
- Connects to database and writes logs synchronously

## Database

- PostgreSQL with timescale addon for optimized timeseries data
- Logs stored as JSONB
- Query DB with normal SQL


# Schema

## logs

- timestamp TIMESTAMPTZ (docker log timestamp)
- raw_log TEXT (raw log line from docker log file)
- stream TEXT (stdout, stderr)
- log JSONB
    - If the raw_log line is parsable as json it is inserted here as JSONB
- metadata JSONB
    - If using kubernetes service account
        - container_id
        - container_name
        - container_image
        - namespace
        - pod_name
        - pod_ip
        - host_ip
    - If using docker daemon
        - container_id
        - container_name
        - container_image
        - container_hostname
        - host_hostname

# Example queries

- Show logs for container

```
SELECT timestamp, log
FROM logs
WHERE metadata ->> 'container_name' = 'some_container_name'
ORDER BY timestamp
DESC LIMIT 10;`
```

- Delete old chunks

```
SELECT drop_chunks(older_than => interval '1 month');
```

- Indexed queries

```
CREATE INDEX ON logs ((metadata ->> 'container_id'), timestamp DESC);
SELECT timestamp FROM logs WHERE metadata ->> 'container_id' = 'some_container' ORDER BY timestamp DESC LIMIT 1;
```

- Free text search

```
SELECT raw_log FROM logs WHERE metadata ->> 'container_name' LIKE '%dispatcher%' AND raw_log LIKE '%ERROR:%';
```

- Histogram search

```
SELECT time_bucket('1 hour', timestamp) bucket, count(*) FROM logs GROUP BY bucket ORDER BY bucket DESC LIMIT 24;
```

# License

Copyright (C) 2019 Øystein Olsen

Licensed under GPL-3.0-only
