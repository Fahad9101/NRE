PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS sources (source_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS securities (security_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, security_id TEXT NOT NULL REFERENCES securities(security_id), source_id TEXT NOT NULL REFERENCES sources(source_id), cluster_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prices (price_id TEXT PRIMARY KEY, security_id TEXT NOT NULL REFERENCES securities(security_id), source_id TEXT NOT NULL REFERENCES sources(source_id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes (event_id TEXT PRIMARY KEY REFERENCES events(event_id), state TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (snapshot_id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
