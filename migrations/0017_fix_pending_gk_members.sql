ALTER TABLE pending_gatekeeper_members DROP CONSTRAINT IF EXISTS pending_gatekeeper_members_pkey;
ALTER TABLE pending_gatekeeper_members ADD PRIMARY KEY (guild_id, member_id);