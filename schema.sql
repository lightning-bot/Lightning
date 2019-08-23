-- Created for PostgreSQL 11

DROP TABLE IF EXISTS cronjobs, staff_roles;

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