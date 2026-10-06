-- Run from the repository root with DuckDB:
--   duckdb -c ".read datasets/macroeconomic-indicators/duckdb/setup.sql"
-- The CSV release remains canonical; these are live views over those files.
CREATE OR REPLACE VIEW countries AS
SELECT * FROM read_csv_auto('datasets/macroeconomic-indicators/source/countries.csv', nullstr='\\N');
CREATE OR REPLACE VIEW sources AS
SELECT * FROM read_csv_auto('datasets/macroeconomic-indicators/source/sources.csv', nullstr='\\N');
CREATE OR REPLACE VIEW indicators AS
SELECT * FROM read_csv_auto('datasets/macroeconomic-indicators/source/indicators.csv', nullstr='\\N');
CREATE OR REPLACE VIEW source_snapshots AS
SELECT * FROM read_csv_auto('datasets/macroeconomic-indicators/source/source_snapshots.csv', nullstr='\\N');
CREATE OR REPLACE VIEW source_series_metadata AS
SELECT * FROM read_csv_auto('datasets/macroeconomic-indicators/source/source_series_metadata.csv', nullstr='\\N');
CREATE OR REPLACE VIEW schema_meta AS
SELECT * FROM read_csv_auto('datasets/macroeconomic-indicators/source/schema_meta.csv', nullstr='\\N');
CREATE OR REPLACE VIEW observations AS
SELECT * FROM read_csv_auto([
  'datasets/macroeconomic-indicators/source/observations/annual/*.csv',
  'datasets/macroeconomic-indicators/source/observations/quarterly/*.csv'
], union_by_name=true, nullstr='\\N');
CREATE OR REPLACE VIEW research_observations AS
SELECT c.serial_no, c.wb_code, c.country_name, c.wb_region, c.income_level,
       i.indicator_code, i.display_name, o.period, o.frequency, o.value,
       i.unit, o.value_status, o.seasonal_adjustment, o.source_id,
       o.source_series_code, o.observation_metadata
FROM observations o
JOIN countries c ON c.wb_code=o.country_code
JOIN indicators i ON i.indicator_code=o.indicator_code;
CREATE OR REPLACE VIEW indicator_coverage AS
SELECT indicator_code, frequency, COUNT(*) AS observation_count,
       COUNT(DISTINCT country_code) AS economy_count,
       MIN(period) AS first_period, MAX(period) AS last_period
FROM observations GROUP BY indicator_code, frequency;
