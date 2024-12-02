CREATE TABLE IF NOT EXISTS automod_metrics
(
    rule_name VARCHAR (200) PRIMARY KEY,
    count BIGINT DEFAULT '0'
);