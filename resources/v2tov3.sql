-- 3.0.0 Migration
-- depends: 


-- Apparently these tables/type are already created...
DROP TABLE IF EXISTS roles;
DROP TABLE IF EXISTS logging;
DROP TABLE IF EXISTS guilds;
DROP TABLE IF EXISTS socket_stats;
DROP TABLE IF EXISTS command_bugs;
DROP TABLE IF EXISTS infractions;
DROP TYPE IF EXISTS log_format_enum;

CREATE TABLE IF NOT EXISTS guilds
(
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    left_at timestamp without time zone,
    owner_id BIGINT NOT NULL,
    whitelisted BOOLEAN DEFAULT 't'
);

CREATE TABLE IF NOT EXISTS roles
(
    guild_id BIGINT,
    user_id BIGINT,
    roles BIGINT [],
    punishment_roles BIGINT [],
    UNIQUE (guild_id, user_id)
);

CREATE TYPE log_format_enum AS ENUM ('minimal with timestamp', 'minimal without timestamp', 'emoji', 'embed');

CREATE TABLE IF NOT EXISTS logging
(
    guild_id BIGINT NOT NULL,
    channel_id BIGINT PRIMARY KEY,
    types TEXT [],
    format log_format_enum DEFAULT 'minimal with timestamp',
    timezone TEXT
);

CREATE TABLE IF NOT EXISTS socket_stats
(
    event VARCHAR (100) PRIMARY KEY,
    count BIGINT DEFAULT '0'
);

CREATE TABLE IF NOT EXISTS command_bugs
(
    token VARCHAR (50) PRIMARY KEY,
    traceback TEXT,
    created_at timestamp without time zone
);

CREATE TABLE IF NOT EXISTS infractions
(
    id int GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    guild_id BIGINT,
    user_id BIGINT,
    moderator_id BIGINT,
    action INT,
    reason VARCHAR (2000),
    created_at timestamp without time zone DEFAULT (now() at time zone 'utc'),
    expiry timestamp without time zone,
    active BOOLEAN DEFAULT 't',
    extra JSONB
);

-- Convert warns to infractions
INSERT INTO infractions (guild_id, user_id, moderator_id, created_at, reason)
SELECT guild_id, user_id, mod_id, timestamp, reason FROM warns;

-- Convert user_restrictions to roles
INSERT INTO roles (guild_id, user_id, punishment_roles)
SELECT guild_id, user_id, ARRAY_AGG(role_id) FROM user_restrictions GROUP BY guild_id, user_id;

alter table "public"."guild_config" add column "toggleroles" bigint[];

-- Move togglerole data over
INSERT INTO guild_config (guild_id, toggleroles)
SELECT guild_id, ARRAY_AGG(role_id) FROM toggleable_roles GROUP BY guild_id
ON CONFLICT (guild_id) DO UPDATE SET toggleroles = EXCLUDED.toggleroles;

-- Generated by migra
alter table "public"."pardoned_warns" drop constraint if exists "pardoned_warns_guild_id_fkey";

alter table "public"."bug_tickets" drop constraint if exists "bug_tickets_pkey";

alter table "public"."command_plonks" drop constraint if exists "command_plonks_pkey";

alter table "public"."pardoned_warns" drop constraint if exists "pardoned_warns_pkey";

alter table "public"."snipe_settings" drop constraint if exists "snipe_settings_pkey";

alter table "public"."sniped_messages" drop constraint if exists "sniped_messages_pkey";

alter table "public"."staff_roles" drop constraint if exists "staff_roles_pkey";

alter table "public"."toggleable_roles" drop constraint if exists "toggleable_roles_pkey";

alter table "public"."user_restrictions" drop constraint if exists "user_restrictions_pkey";

alter table "public"."userlogs" drop constraint if exists "userlogs_pkey";

alter table "public"."warns" drop constraint if exists "warns_pkey" CASCADE;

drop index if exists "public"."bug_tickets_pkey";

drop index if exists "public"."command_plonks_pkey";

drop index if exists "public"."command_plonks_uniq_idx";

drop index if exists "public"."commands_usage_command_name_idx";

drop index if exists "public"."commands_usage_used_at_idx";

drop index if exists "public"."commands_usage_user_id_idx";

drop index if exists "public"."pardoned_warns_pkey";

drop index if exists "public"."pardoned_warns_uniq_idx";

drop index if exists "public"."snipe_settings_pkey";

drop index if exists "public"."sniped_messages_pkey";

drop index if exists "public"."staff_roles_pkey";

drop index if exists "public"."toggleable_roles_pkey";

drop index if exists "public"."user_restrictions_pkey";

drop index if exists "public"."userlogs_pkey";

drop index if exists "public"."warns_pkey";

drop index if exists "public"."warns_uniq_idx";

drop index if exists "public"."commands_usage_guild_id_idx";

drop table "public"."bug_tickets";

drop table "public"."command_plonks";

drop table "public"."pardoned_warns";

drop table "public"."snipe_settings";

drop table "public"."sniped_messages";

drop table "public"."staff_roles";

drop table "public"."toggleable_roles";

drop table "public"."user_restrictions";

drop table "public"."userlogs";

drop table "public"."warns";

alter table "public"."commands_usage" add column "channel_id" bigint;

alter table "public"."guild_config" add column "flags" integer;

alter table "public"."guild_config" add column "permissions" jsonb;

alter table "public"."guild_mod_config" drop column "log_channels";

alter table "public"."guild_mod_config" drop column if exists "log_format";

alter table "public"."guild_mod_config" add column "automod_join_threshold_seconds" integer;

alter table "public"."guild_mod_config" add column "automod_join_threshold_users" integer;

alter table "public"."guild_mod_config" add column "raid_mode" boolean default false;

alter table "public"."guild_mod_config" add column "temp_mute_role_id" bigint;

alter table "public"."guild_mod_config" alter column "warn_ban" set data type bigint using "warn_ban"::bigint;

alter table "public"."guild_mod_config" alter column "warn_kick" set data type bigint using "warn_kick"::bigint;

alter table "public"."nin_updates" alter column "webhook_token" set data type character varying(100) using "webhook_token"::character varying(100);

drop sequence if exists "public"."bug_tickets_id_seq";

drop sequence if exists "public"."command_plonks_id_seq";

drop sequence if exists "public"."pardoned_warns_warn_id_seq";

drop sequence if exists "public"."warns_warn_id_seq";

CREATE INDEX commands_usage_guild_id_idx ON public.commands_usage USING btree (user_id, used_at, command_name);