CREATE TABLE IF NOT EXISTS guild_gatekeeper_config
(
    guild_id BIGINT NOT NULL REFERENCES guilds (id) ON DELETE CASCADE PRIMARY KEY,
    active BOOLEAN DEFAULT 'f',
    role_id BIGINT,
    verification_channel_id BIGINT,
    last_verified_member_id BIGINT
);

CREATE TABLE IF NOT EXISTS pending_gatekeeper_members
(
    guild_id BIGINT NOT NULL REFERENCES guilds (id) ON DELETE CASCADE PRIMARY KEY
);