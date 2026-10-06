import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent if (HERE.parent/"scripts"/"build_database.py").is_file() else HERE
SCRIPT_DIR=ROOT/"scripts" if (ROOT/"scripts").is_dir() else ROOT
sys.path.insert(0,str(SCRIPT_DIR))
def load_module(name,filename):
    spec=importlib.util.spec_from_file_location(name,HERE/filename)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

builder=load_module("build_database",str(SCRIPT_DIR/"build_database.py"))
exporter=load_module("prepare_source_data",str(SCRIPT_DIR/"prepare_source_data.py"))
SCHEMA=ROOT/"schema"/"sqlite.sql" if (ROOT/"schema"/"sqlite.sql").is_file() else ROOT/"sqlite_schema.sql"


class BuildDatabaseTests(unittest.TestCase):
    def test_export_rebuild_preserves_rows_nulls_metadata_and_escaped_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=root/"original.sqlite"; source=root/"source"; rebuilt=root/"rebuilt.sqlite"
            con=sqlite3.connect(original); con.executescript(SCHEMA.read_text(encoding="utf-8"))
            con.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",("src","Publisher","Dataset","https://example.test",None,"Terms","Credit","2026-01-01"))
            con.execute("INSERT INTO countries VALUES(?,?,?,?,?,?,?,?,?,?)",(1,"IND","IN","India \\N","R","South Asia","I","Income",None,None))
            con.execute("INSERT INTO indicators VALUES(?,?,?,?,?,?,?,?,?)",("population_total_annual","Population","annual","people","Population count","src","POP",None,"loaded"))
            con.execute("INSERT INTO schema_meta VALUES(?,?)",("release_date","2026-01-01"))
            con.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?)",("IND","population_total_annual","2025","annual",1.25,None,"observed","src","POP",None,"{}"))
            con.commit(); con.close()
            exporter.export(original,source)
            builder.load(source,SCHEMA,rebuilt)
            builder.verify_equal(rebuilt,original)
            con=sqlite3.connect(rebuilt)
            self.assertEqual(con.execute("SELECT country_name FROM countries").fetchone()[0],"India \\N")
            self.assertIsNone(con.execute("SELECT api_url FROM sources").fetchone()[0])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM research_observations").fetchone()[0],1)
            con.close()

    def test_modified_source_file_fails_checksum_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=root/"original.sqlite"; source=root/"source"; rebuilt=root/"rebuilt.sqlite"
            con=sqlite3.connect(original); con.executescript(SCHEMA.read_text(encoding="utf-8"))
            con.execute("INSERT INTO schema_meta VALUES('release_date','2026-01-01')"); con.commit(); con.close()
            exporter.export(original,source)
            with (source/"sources.csv").open("a",encoding="utf-8") as f: f.write("tampered\n")
            with self.assertRaisesRegex(ValueError,"Checksum mismatch"):
                builder.load(source,SCHEMA,rebuilt)


if __name__=="__main__": unittest.main()
