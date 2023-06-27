ALTER TABLE timers ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';

CREATE TABLE IF NOT EXISTS user_settings
(
    user_id BIGINT PRIMARY KEY,
    timezone TEXT
);