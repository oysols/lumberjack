BEGIN;
CREATE TABLE logs (
    time                   TIMESTAMPTZ       NOT NULL,
    meta                   TEXT              NULL,
    data                   JSONB             NULL
);
SELECT create_hypertable('logs', 'time');
COMMIT;
