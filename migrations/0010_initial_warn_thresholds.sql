ALTER TABLE guild_automod_config ADD COLUMN IF NOT EXISTS warn_threshold SMALLINT;
ALTER TABLE guild_automod_config ADD COLUMN IF NOT EXISTS warn_punishment TEXT;

-- In v5, we'll remove warn_kick and warn_ban