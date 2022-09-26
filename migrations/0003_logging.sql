ALTER TABLE logging ADD COLUMN webhook_url TEXT;

CREATE TABLE IF NOT EXISTS pastes
(
    code TEXT,
    delete_token TEXT
);

DROP TABLE IF EXISTS _yoyo_log;
DROP TABLE IF EXISTS yoyo_lock;
DROP TABLE IF EXISTS _yoyo_migration;
DROP TABLE IF EXISTS _yoyo_version;