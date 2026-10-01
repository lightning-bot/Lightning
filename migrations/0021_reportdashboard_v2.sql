-- We need to add a column to store the ID of the reported user
ALTER TABLE message_reports ADD COLUMN reported_user_id BIGINT;

-- Add a column to track the view version of the report
ALTER TABLE message_reports ADD COLUMN view_version SMALLINT;

-- Set existing records to version 1
UPDATE message_reports SET view_version = 1;

ALTER TABLE message_reports ALTER COLUMN view_version SET DEFAULT 2;

-- Create a specialized view so that we exclude the 'Report Message' command from public command stats
CREATE VIEW public_command_stats AS SELECT * FROM command_stats WHERE command_name != 'Report Message';
