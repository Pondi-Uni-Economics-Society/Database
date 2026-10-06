-- Canonical SQLite schema for the Society macroeconomic research dataset.
-- Apply in one transaction; data are loaded from the reviewed CSV source files.
PRAGMA foreign_keys = ON;
BEGIN;

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    publisher TEXT NOT NULL,
    dataset_title TEXT NOT NULL,
    landing_url TEXT NOT NULL,
    api_url TEXT,
    terms TEXT NOT NULL,
    attribution TEXT NOT NULL,
    accessed_on TEXT NOT NULL
);
CREATE TABLE countries (
    serial_no INTEGER PRIMARY KEY,
    wb_code TEXT NOT NULL UNIQUE,
    iso2_code TEXT NOT NULL,
    country_name TEXT NOT NULL,
    wb_region_code TEXT,
    wb_region TEXT,
    income_level_code TEXT,
    income_level TEXT,
    lending_type_code TEXT,
    lending_type TEXT
);
CREATE TABLE indicators (
    indicator_code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('annual','quarterly')),
    unit TEXT NOT NULL,
    definition TEXT NOT NULL,
    source_id TEXT REFERENCES sources(source_id),
    source_series_code TEXT,
    calculation TEXT,
    availability TEXT NOT NULL DEFAULT 'loaded'
);
CREATE TABLE source_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    retrieved_at TEXT NOT NULL,
    request_url TEXT NOT NULL,
    returned_rows INTEGER NOT NULL,
    provider_update_date TEXT,
    notes TEXT
);
CREATE TABLE source_series_metadata (
    country_code TEXT NOT NULL REFERENCES countries(wb_code),
    indicator_code TEXT NOT NULL REFERENCES indicators(indicator_code),
    source_series_code TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    seasonal_adjustment TEXT,
    series_metadata TEXT NOT NULL CHECK (json_valid(series_metadata)),
    PRIMARY KEY(country_code, indicator_code, source_series_code)
);
CREATE TABLE observations (
    country_code TEXT NOT NULL REFERENCES countries(wb_code),
    indicator_code TEXT NOT NULL REFERENCES indicators(indicator_code),
    period TEXT NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('annual','quarterly')),
    value REAL NOT NULL CHECK (value = value),
    raw_value TEXT,
    value_status TEXT NOT NULL CHECK (value_status IN ('observed','estimated','derived','forecast','provisional')),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_series_code TEXT NOT NULL,
    seasonal_adjustment TEXT,
    observation_metadata TEXT CHECK (observation_metadata IS NULL OR json_valid(observation_metadata)),
    PRIMARY KEY(country_code, indicator_code, period, source_series_code),
    CHECK ((frequency='annual' AND length(period)=4 AND period NOT GLOB '*[^0-9]*') OR
           (frequency='quarterly' AND length(period)=7 AND substr(period,6,2) IN ('Q1','Q2','Q3','Q4') AND substr(period,1,4) NOT GLOB '*[^0-9]*'))
);
CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE INDEX idx_observations_country_indicator ON observations(country_code, indicator_code);
CREATE INDEX idx_observations_indicator_period ON observations(indicator_code, period);
CREATE INDEX idx_observations_period ON observations(period);

CREATE VIEW indicator_coverage AS
SELECT indicator_code, frequency, COUNT(*) AS observation_count,
       COUNT(DISTINCT country_code) AS economy_count,
       MIN(period) AS first_period, MAX(period) AS last_period
FROM observations GROUP BY indicator_code, frequency;
CREATE VIEW research_observations AS
SELECT c.serial_no, c.wb_code, c.country_name, c.wb_region, c.income_level,
       i.indicator_code, i.display_name, o.period, o.frequency, o.value,
       i.unit, o.value_status, o.seasonal_adjustment, o.source_id,
       o.source_series_code, o.observation_metadata
FROM observations o
JOIN countries c ON c.wb_code=o.country_code
JOIN indicators i ON i.indicator_code=o.indicator_code;
COMMIT;
