BEGIN;
CREATE TABLE logs (
    timestamp TIMESTAMPTZ NOT NULL,
    raw_log TEXT NULL,
    stream TEXT NOT NULL,
    log JSONB NOT NULL,
    metadata JSONB NOT NULL
);
SELECT create_hypertable('logs', 'timestamp');
COMMIT;
