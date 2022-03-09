-- 4.0.0
-- depends: 20211013_01_343eu-3-3-0

ALTER TABLE guild_mod_config DROP COLUMN temp_mute_role_id;

ALTER TABLE guild_config RENAME COLUMN prefix TO prefixes;