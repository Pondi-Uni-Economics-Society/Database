-- Economics Society research starter database (PostgreSQL)
-- Stores dataset metadata, provenance, series definitions, and cleaned observations.
-- Do not put credentials or identifiable/restricted participant data in this database.

BEGIN;

CREATE TABLE IF NOT EXISTS sources (
    source_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    publisher       text NOT NULL,
    title           text NOT NULL,
    landing_url     text NOT NULL,
    download_url    text,
    license_name    text,
    license_url     text,
    citation_text   text,
    accessed_on     date NOT NULL,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug             text NOT NULL UNIQUE
                     CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    title            text NOT NULL,
    description      text NOT NULL,
    subject          text NOT NULL,
    geography_scope  text,
    license_name     text,
    license_url      text,
    status           text NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft', 'review', 'released', 'archived')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dataset_sources (
    dataset_id           bigint NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    source_id            bigint NOT NULL REFERENCES sources(source_id) ON DELETE RESTRICT,
    source_role          text NOT NULL DEFAULT 'primary'
                         CHECK (source_role IN ('primary', 'supplementary', 'methodology')),
    transformation_notes text,
    PRIMARY KEY (dataset_id, source_id)
);

CREATE TABLE IF NOT EXISTS dataset_releases (
    release_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id       bigint NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    version          text NOT NULL,
    released_on      date NOT NULL,
    changelog        text NOT NULL,
    artifact_url     text,
    UNIQUE (dataset_id, version)
);

CREATE TABLE IF NOT EXISTS series (
    series_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id          bigint NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    code                text NOT NULL,
    name                text NOT NULL,
    description         text,
    unit                text NOT NULL,
    frequency           text NOT NULL
                        CHECK (frequency IN ('annual', 'quarterly', 'monthly', 'weekly', 'daily', 'irregular')),
    geography_name      text,
    geography_code      text NOT NULL DEFAULT 'ALL',
    geography_level     text,
    seasonal_adjustment text,
    UNIQUE (dataset_id, code, geography_code)
);

CREATE TABLE IF NOT EXISTS observations (
    series_id         bigint NOT NULL REFERENCES series(series_id) ON DELETE CASCADE,
    period_start      date NOT NULL,
    value             numeric(24, 8),
    raw_value         text,
    status            text NOT NULL DEFAULT 'observed'
                      CHECK (status IN ('observed', 'estimated', 'provisional', 'revised', 'missing')),
    observation_note  text,
    PRIMARY KEY (series_id, period_start),
    CHECK (
        (status = 'missing' AND value IS NULL)
        OR (status <> 'missing' AND value IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS cleaning_runs (
    cleaning_run_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id       bigint NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    version          text NOT NULL,
    ran_at           timestamptz NOT NULL DEFAULT now(),
    script_path      text NOT NULL,
    script_commit    text,
    notes            text NOT NULL,
    UNIQUE (dataset_id, version)
);

CREATE INDEX IF NOT EXISTS idx_datasets_subject_status
    ON datasets (subject, status);
CREATE INDEX IF NOT EXISTS idx_series_dataset
    ON series (dataset_id);
CREATE INDEX IF NOT EXISTS idx_series_code
    ON series (code);
CREATE INDEX IF NOT EXISTS idx_observations_period
    ON observations (period_start);

COMMIT;
