ALTER TABLE IF EXISTS guild_gatekeeper_config ADD COLUMN IF NOT EXISTS honeypot BOOLEAN DEFAULT 'f';

ALTER TABLE IF EXISTS guild_gatekeeper_config ADD COLUMN IF NOT EXISTS verification_message_id BIGINT;