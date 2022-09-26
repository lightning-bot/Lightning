ALTER TABLE logging ADD COLUMN webhook_url TEXT;

CREATE TABLE IF NOT EXISTS pastes
(
    code TEXT,
    delete_token TEXT
);
