ALTER TABLE guild_mod_config ADD COLUMN IF NOT EXISTS footer_message TEXT;
ALTER TABLE guild_mod_config ADD COLUMN IF NOT EXISTS dm_messages BOOLEAN DEFAULT 'f';

UPDATE guild_mod_config SET dm_messages = 't'; -- Enable legacy behavior for current guilds
