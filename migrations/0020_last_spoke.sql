-- Last Spoke Tracking

-- This might turn more specific for AutoMod, but it's simple for now
CREATE TABLE IF NOT EXISTS spoke_tracking (
    user_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    first_spoke_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL,
    last_spoke_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'UTC'),
    PRIMARY KEY (user_id, guild_id)
);