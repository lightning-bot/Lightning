-- Tables and Types needed for web.lightningbot.app
CREATE TABLE IF NOT EXISTS web_customers
(
    user_id BIGINT NOT NULL PRIMARY KEY,
    stripe_id TEXT NOT NULL
);

DO $$ BEGIN
    CREATE TYPE premium_code_type AS ENUM ("LIGHTNING_FUN", "LIGHTNING_PREMIUM");
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS premium_codes
(
    code TEXT NOT NULL,
    type premium_code_type,
    stripe_transaction_id TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
    expires BIGINT
);

CREATE TABLE IF NOT EXISTS premium_guilds
(
    guild_id BIGINT NOT NULL REFERENCES guilds (id),
    redemption_code TEXT REFERENCES premium_codes (code) ON DELETE CASCADE PRIMARY KEY
);

-- CREATE TABLE IF NOT EXISTS premium_subs
-- (
--    user_id BIGINT,
-- );

-- CREATE TABLE IF NOT EXISTS premium_guilds
-- (
--    guild_id BIGINT NOT NULL REFERENCES guilds (id) ON DELETE CASCADE PRIMARY KEY,
--    flags INT,
-- );