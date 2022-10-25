ALTER TABLE guild_config DROP COLUMN IF EXISTS flags;


ALTER TABLE commands_usage ADD COLUMN IF NOT EXISTS application_command BOOLEAN;
ALTER TABLE IF EXISTS commands_usage RENAME TO command_stats;