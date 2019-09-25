# Lumberjack

Log aggregation and storeage of docker container logs from kubernetes or single docker host.

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

```
    SELECT timestamp, log
    FROM logs
    WHERE metadata ->> 'container_name' = 'some_container_name'
    ORDER BY timestamp
    DESC LIMIT 10;`
```
