DROP TABLE IF EXISTS cronjobs;

CREATE TABLE cronjobs
(
    id SERIAL PRIMARY KEY,
    expiry timestamp without time zone,
    created timestamp without time zone,
    event TEXT,
    extra JSONB
);