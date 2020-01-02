-- Created for PostgreSQL 11

-- Just store the timestamps as utcnow(). 
-- Makes my life easier
CREATE TABLE IF NOT EXISTS timers
(
    id SERIAL PRIMARY KEY,
    expiry timestamp without time zone,
    created timestamp without time zone DEFAULT (now() at time zone 'utc'),
    event TEXT,
    extra JSONB
);

CREATE TABLE IF NOT EXISTS staff_roles
(
    guild_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    perms TEXT NOT NULL,
    CONSTRAINT staff_roles_pkey PRIMARY KEY (guild_id, role_id, perms)
);

CREATE TABLE IF NOT EXISTS userlogs
(
    guild_id BIGINT PRIMARY KEY,
    userlog JSONB
);

CREATE TABLE IF NOT EXISTS user_restrictions
(
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    CONSTRAINT user_restrictions_pkey PRIMARY KEY (guild_id, user_id, role_id)
);

CREATE TABLE IF NOT EXISTS guild_mod_config
(
    guild_id BIGINT PRIMARY KEY,
    mute_role_id BIGINT,
    log_channels JSONB
);

CREATE TABLE IF NOT EXISTS toggleable_roles
(
    guild_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    CONSTRAINT toggleable_roles_pkey PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS commands_usage
(
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT,
    user_id BIGINT,
    used_at TIMESTAMP WITHOUT TIME ZONE,-- DEFAULT (now() at time zone 'utc'),
    command_name TEXT,
    failure BOOLEAN
);

CREATE INDEX IF NOT EXISTS commands_usage_guild_id_idx ON commands_usage (guild_id);
CREATE INDEX IF NOT EXISTS commands_usage_user_id_idx ON commands_usage (user_id);
CREATE INDEX IF NOT EXISTS commands_usage_used_at_idx ON commands_usage (used_at);
CREATE INDEX IF NOT EXISTS commands_usage_command_name_idx ON commands_usage (command_name);

CREATE TABLE IF NOT EXISTS bug_tickets
(
    id SERIAL PRIMARY KEY,
    guild_id BIGINT,
    channel_id BIGINT,
    message_id BIGINT,
    status TEXT,
    created TIMESTAMP WITHOUT TIME ZONE,
    ticket_info JSONB
);

CREATE TABLE IF NOT EXISTS sniped_messages
(
    guild_id BIGINT,
    channel_id BIGINT PRIMARY KEY,
    message VARCHAR(2000),
    user_id BIGINT,
    timestamp TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS snipe_settings
(
    guild_id BIGINT PRIMARY KEY,
    channel_ids BIGINT [],
    user_ids BIGINT []
);

ALTER TABLE guild_mod_config ADD COLUMN IF NOT EXISTS warn_ban SMALLINT;
ALTER TABLE guild_mod_config ADD COLUMN IF NOT EXISTS warn_kick SMALLINT;
ALTER TABLE guild_mod_config ADD COLUMN IF NOT EXISTS log_format SMALLINT;
DROP TABLE IF EXISTS auto_roles;

CREATE TABLE IF NOT EXISTS nin_updates
(
    guild_id BIGINT PRIMARY KEY,
    id BIGINT,
    webhook_token VARCHAR (500)
);

CREATE TABLE IF NOT EXISTS guild_config
(
    guild_id BIGINT PRIMARY KEY,
    prefix TEXT [],
    autorole BIGINT
);

CREATE TABLE IF NOT EXISTS command_plonks
(
    id SERIAL PRIMARY KEY,
    guild_id BIGINT,
    channel_id BIGINT [],
    name TEXT,
    whitelist BOOLEAN
);

CREATE UNIQUE INDEX IF NOT EXISTS command_plonks_uniq_idx ON command_plonks (guild_id, channel_id, name, whitelist);

CREATE TABLE IF NOT EXISTS warns
(
    guild_id BIGINT NOT NULL,
    warn_id SERIAL,
    user_id BIGINT,
    mod_id BIGINT,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
    reason TEXT,
    pardoned BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (guild_id, warn_id)
);

CREATE TABLE IF NOT EXISTS pardoned_warns
(
    guild_id BIGINT,
    warn_id SERIAL,
    mod_id BIGINT,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
    FOREIGN KEY (guild_id, warn_id) REFERENCES warns (guild_id, warn_id) ON DELETE CASCADE,
    CONSTRAINT pardoned_warns_pkey PRIMARY KEY (guild_id, warn_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS warns_uniq_idx ON warns (warn_id, user_id, mod_id, timestamp, reason, pardoned);
CREATE UNIQUE INDEX IF NOT EXISTS pardoned_warns_uniq_idx ON pardoned_warns (warn_id, mod_id, timestamp);


ALTER TABLE guild_mod_config ADD COLUMN IF NOT EXISTS muted BIGINT [];