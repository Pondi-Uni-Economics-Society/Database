import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("health_check.py")
SPEC = importlib.util.spec_from_file_location("health_check", MODULE)
health_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health_check)


def make_db(path: Path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE countries(serial_no INTEGER PRIMARY KEY, wb_code TEXT UNIQUE NOT NULL,
            iso2_code TEXT NOT NULL,country_name TEXT NOT NULL,wb_region_code TEXT,wb_region TEXT,
            income_level_code TEXT,income_level TEXT,lending_type_code TEXT,lending_type TEXT);
        CREATE TABLE sources(source_id TEXT PRIMARY KEY,publisher TEXT NOT NULL,dataset_title TEXT NOT NULL,
            landing_url TEXT NOT NULL,api_url TEXT,terms TEXT NOT NULL,attribution TEXT NOT NULL,accessed_on TEXT NOT NULL);
        CREATE TABLE indicators(indicator_code TEXT PRIMARY KEY,display_name TEXT NOT NULL,frequency TEXT NOT NULL,
            unit TEXT NOT NULL,definition TEXT NOT NULL,source_id TEXT REFERENCES sources(source_id),
            source_series_code TEXT,calculation TEXT,availability TEXT NOT NULL DEFAULT 'loaded');
        CREATE TABLE source_snapshots(snapshot_id INTEGER PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(source_id),
            retrieved_at TEXT NOT NULL,request_url TEXT NOT NULL,returned_rows INTEGER NOT NULL,provider_update_date TEXT,notes TEXT);
        CREATE TABLE source_series_metadata(country_code TEXT NOT NULL REFERENCES countries(wb_code),
            indicator_code TEXT NOT NULL REFERENCES indicators(indicator_code),source_series_code TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES sources(source_id),seasonal_adjustment TEXT,series_metadata TEXT NOT NULL,
            PRIMARY KEY(country_code,indicator_code,source_series_code));
        CREATE TABLE observations(country_code TEXT NOT NULL REFERENCES countries(wb_code),
            indicator_code TEXT NOT NULL REFERENCES indicators(indicator_code),period TEXT NOT NULL,frequency TEXT NOT NULL,
            value REAL NOT NULL,raw_value TEXT,value_status TEXT NOT NULL CHECK(value_status IN
            ('observed','estimated','derived','forecast','provisional')),source_id TEXT NOT NULL REFERENCES sources(source_id),
            source_series_code TEXT NOT NULL,seasonal_adjustment TEXT,observation_metadata TEXT,
            PRIMARY KEY(country_code,indicator_code,period,source_series_code));
        CREATE TABLE schema_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE VIEW indicator_coverage AS SELECT indicator_code,frequency,COUNT(*) observation_count,
            COUNT(DISTINCT country_code) economy_count,MIN(period) first_period,MAX(period) last_period
            FROM observations GROUP BY indicator_code,frequency;
        CREATE VIEW research_observations AS SELECT c.serial_no,c.wb_code,c.country_name,c.wb_region,c.income_level,
            i.indicator_code,i.display_name,o.period,o.frequency,o.value,i.unit,o.value_status,
            o.seasonal_adjustment,o.source_id,o.source_series_code,o.observation_metadata
            FROM observations o JOIN countries c ON c.wb_code=o.country_code
            JOIN indicators i ON i.indicator_code=o.indicator_code;
        CREATE INDEX idx_observations_country_indicator ON observations(country_code,indicator_code);
        CREATE INDEX idx_observations_indicator_period ON observations(indicator_code,period);
        CREATE INDEX idx_observations_period ON observations(period);
        INSERT INTO countries VALUES(1,'IND','IN','India',NULL,'South Asia',NULL,'Lower middle income',NULL,NULL);
        INSERT INTO sources VALUES('wb','World Bank','WDI','https://example.test',NULL,'terms','credit','2026-01-01');
        INSERT INTO indicators VALUES('population_total_annual','Population','annual','people','Population','wb','SP.POP.TOTL',NULL,'loaded');
        INSERT INTO source_series_metadata VALUES('IND','population_total_annual','SP.POP.TOTL','wb',NULL,'{}');
        INSERT INTO observations VALUES('IND','population_total_annual','2024','annual',100,NULL,'observed','wb','SP.POP.TOTL',NULL,'{}');
        INSERT INTO observations VALUES('IND','population_total_annual','2025','annual',101,NULL,'observed','wb','SP.POP.TOTL',NULL,'{}');
    """)
    con.commit(); con.close()


class HealthCheckTests(unittest.TestCase):
    def audit(self, root: Path):
        report = health_check.Audit(root / "sample.sqlite", None, 1).run()
        return report

    def test_clean_sample_supports_readback_and_indexed_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); make_db(root / "sample.sqlite")
            report = self.audit(root)
            by_name = {c["name"]: c for c in report["checks"]}
            self.assertEqual(by_name["SQLite integrity_check"]["status"], "pass")
            self.assertEqual(by_name["country lookup by code"]["status"], "pass")
            self.assertIn("SQLite page accounting", by_name)

    def test_orphan_foreign_key_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=root/"sample.sqlite"; make_db(db)
            con=sqlite3.connect(db); con.execute("PRAGMA foreign_keys=OFF")
            con.execute("INSERT INTO observations VALUES('XXX','population_total_annual','2026','annual',1,NULL,'observed','wb','SP.POP.TOTL',NULL,'{}')"); con.commit(); con.close()
            report=self.audit(root)
            checks={c["name"]:c for c in report["checks"]}
            self.assertEqual(checks["foreign_key_check"]["status"],"fail")
            self.assertTrue(report["critical_failure"])

    def test_invalid_period_and_metadata_json_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=root/"sample.sqlite"; make_db(db)
            con=sqlite3.connect(db)
            con.execute("INSERT INTO observations VALUES('IND','population_total_annual','20XX','annual',1,NULL,'observed','wb','SP.POP.TOTL',NULL,'not-json')"); con.commit(); con.close()
            checks={c["name"]:c for c in self.audit(root)["checks"]}
            self.assertEqual(checks["period labels valid"]["status"],"fail")
            self.assertEqual(checks["observation metadata JSON"]["status"],"fail")


if __name__ == "__main__":
    unittest.main()
