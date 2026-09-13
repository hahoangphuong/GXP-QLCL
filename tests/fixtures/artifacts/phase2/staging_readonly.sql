CREATE TABLE company (
    id TEXT PRIMARY KEY
);

CREATE TABLE site (
    id TEXT PRIMARY KEY,
    company_id TEXT
);

CREATE TABLE "case" (
    id TEXT PRIMARY KEY,
    site_id TEXT
);

CREATE TABLE certificate (
    id TEXT PRIMARY KEY,
    case_id TEXT
);

CREATE TABLE legacy_id_map (
    id TEXT PRIMARY KEY,
    entity_type TEXT,
    legacy_id INTEGER
);
