BEGIN;
CREATE TABLE logs (
    time                   TIMESTAMPTZ       NOT NULL,
    meta                   TEXT              NULL,
    data                   JSONB             NULL,
    PRIMARY KEY(time)
);
SELECT create_hypertable('logs', 'time');
COMMIT;
