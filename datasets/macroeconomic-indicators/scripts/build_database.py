#!/usr/bin/env python3
"""Build the canonical SQLite database from the reviewed CSV source release."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

LOAD_ORDER = ("sources", "countries", "indicators", "source_snapshots", "source_series_metadata", "schema_meta", "observations")
TABLE_FILES = {"sources.csv":"sources", "countries.csv":"countries", "indicators.csv":"indicators", "source_snapshots.csv":"source_snapshots", "source_series_metadata.csv":"source_series_metadata", "schema_meta.csv":"schema_meta"}


def decode(value):
    if value == r"\N":
        return None
    if value.startswith(r"\\"):
        return value[1:]
    return value


def load(source: Path, schema: Path, output: Path):
    manifest_path=source/"release.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported release source format")
    files=manifest.get("files",{})
    expected=set(TABLE_FILES)|{k for k in files if k.startswith("observations/") and k.endswith(".csv")}
    if set(files)!=expected:
        raise ValueError("Release manifest contains unexpected or missing source files")
    output=output.resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    tempdir=Path(tempfile.mkdtemp(prefix="macro-db-build-",dir=output.parent))
    building=tempdir/"built.sqlite"
    con=sqlite3.connect(building)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript(schema.read_text(encoding="utf-8"))
        manifest_table_files=manifest.get("tables",{})
        for table in LOAD_ORDER:
            paths=[]
            if table=="observations":
                paths=sorted(k for k in files if k.startswith("observations/") and k.endswith(".csv"))
            else:
                filename=next((name for name,target in TABLE_FILES.items() if target==table),None)
                if filename and filename in files: paths=[filename]
            for rel in paths:
                path=(source/rel).resolve()
                if source.resolve() not in path.parents:
                    raise ValueError(f"Unsafe source path: {rel}")
                spec=files[rel]
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                if digest!=spec["sha256"]: raise ValueError(f"Checksum mismatch: {rel}")
                with path.open("r",encoding="utf-8",newline="") as f:
                    reader=csv.reader(f)
                    header=next(reader)
                    if not header or any(not col for col in header): raise ValueError(f"Invalid CSV header: {rel}")
                    placeholders=",".join("?" for _ in header)
                    quoted=",".join('"'+col.replace('"','""')+'"' for col in header)
                    sql=f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
                    count=0
                    for row in reader:
                        if len(row)!=len(header): raise ValueError(f"Wrong column count at {rel}:{reader.line_num}")
                        con.execute(sql,[decode(v) for v in row]); count+=1
                if count!=spec["rows"]: raise ValueError(f"Row-count mismatch in {rel}: {count} != {spec['rows']}")
        con.commit()
        integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity!="ok": raise ValueError(f"SQLite integrity failure: {integrity}")
        fk=con.execute("PRAGMA foreign_key_check").fetchone()
        if fk: raise ValueError(f"Foreign-key violation: {fk}")
        counts={table:con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in LOAD_ORDER}
    except Exception:
        con.close(); shutil.rmtree(tempdir,ignore_errors=True); raise
    con.close()
    os.replace(building,output); shutil.rmtree(tempdir,ignore_errors=True)
    return counts


def verify_equal(candidate: Path, original: Path):
    a=sqlite3.connect(f"file:{candidate.resolve()}?mode=ro",uri=True)
    b=sqlite3.connect(f"file:{original.resolve()}?mode=ro",uri=True)
    try:
        for table in LOAD_ORDER:
            info=a.execute(f'PRAGMA table_info("{table}")').fetchall()
            pk=[r[1] for r in sorted((r for r in info if r[5]),key=lambda r:r[5])]
            order=pk or [r[1] for r in info]
            order_sql=",".join('"'+col.replace('"','""')+'"' for col in order)
            qa=f'SELECT * FROM "{table}" ORDER BY {order_sql}'
            qb=qa
            rows_a=a.execute(qa); rows_b=b.execute(qb)
            while True:
                ra=rows_a.fetchmany(2000); rb=rows_b.fetchmany(2000)
                if len(ra)!=len(rb): raise ValueError(f"Rebuild differs from source database in table {table}")
                for row_no,(left,right) in enumerate(zip(ra,rb),1):
                    for col_no,(x,y) in enumerate(zip(left,right),1):
                        same=(math.isclose(x,y,rel_tol=1e-14,abs_tol=1e-14) if isinstance(x,(int,float)) and isinstance(y,(int,float)) else x==y)
                        if not same:
                            raise ValueError(f"Rebuild differs from source database in table {table}, batch row {row_no}, column {col_no}: {x!r} != {y!r}")
                if not ra: break
    finally: a.close(); b.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=Path(__file__).resolve().parents[1]/"source")
    parser.add_argument("--schema",type=Path,default=Path(__file__).resolve().parents[1]/"schema"/"sqlite.sql")
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parents[1]/"macro_research.sqlite")
    parser.add_argument("--verify-against",type=Path,help="Compare every rebuilt row to a previous SQLite release")
    args=parser.parse_args()
    counts=load(args.source,args.schema,args.output)
    if args.verify_against: verify_equal(args.output,args.verify_against)
    print(json.dumps({"database":str(args.output.resolve()),"counts":counts,"verified_against":str(args.verify_against) if args.verify_against else None},indent=2))


if __name__=="__main__": main()
