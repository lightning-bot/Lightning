-- Created for PostgreSQL 11

DROP TABLE IF EXISTS cronjobs, staff_roles, userlogs, user_restrictions;

-- Just store the timestamps as utcnow(). 
-- Makes my life easier
CREATE TABLE cronjobs
(
    id SERIAL PRIMARY KEY,
    expiry timestamp without time zone,
    created timestamp without time zone,
    event TEXT,
    extra JSONB
);

CREATE TABLE staff_roles
(
    guild_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    perms TEXT NOT NULL,
    CONSTRAINT staff_roles_pkey PRIMARY KEY (guild_id, role_id, perms)
);

CREATE TABLE userlogs
(
    guild_id BIGINT PRIMARY KEY,
    userlog JSONB
);

CREATE TABLE user_restrictions
(
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    CONSTRAINT user_restrictions_pkey PRIMARY KEY (guild_id, user_id, role_id)
);

CREATE TABLE guild_mod_config
(
    guild_id BIGINT PRIMARY KEY,
    mute_role_id BIGINT,
    log_channels JSONB
);

CREATE TABLE toggleable_roles
(
    guild_id BIGINT PRIMARY KEY,
    role_id BIGINT
);

CREATE TABLE auto_roles
(
    guild_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    CONSTRAINT auto_roles_pkey PRIMARY KEY (guild_id, role_id)
);