CREATE TABLE IF NOT EXISTS welcomer (
    guild_id BIGINT PRIMARY KEY,
    leave_message TEXT,
    leave_channel BIGINT,
    join_message TEXT,
    join_channel BIGINT
);
