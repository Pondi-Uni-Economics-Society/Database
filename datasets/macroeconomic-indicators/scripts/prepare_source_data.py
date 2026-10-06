#!/usr/bin/env python3
"""Export a reviewed SQLite release into deterministic, readable CSV source files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import shutil
import tempfile
from pathlib import Path

TABLES = {
    "countries": ("countries.csv", "wb_code"),
    "sources": ("sources.csv", "source_id"),
    "indicators": ("indicators.csv", "indicator_code"),
    "source_snapshots": ("source_snapshots.csv", "snapshot_id"),
    "source_series_metadata": ("source_series_metadata.csv", "country_code,indicator_code,source_series_code"),
    "schema_meta": ("schema_meta.csv", "key"),
}
NULL = r"\N"
MAX_PARTITION_BYTES = 1_500_000


def checksum(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): digest.update(block)
    return digest.hexdigest()


def encode(value):
    if value is None:
        return NULL
    if isinstance(value, str) and (value == NULL or value.startswith("\\")):
        return "\\" + value
    return value


def _export_into(database: Path, output: Path):
    con = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    try:
        for table, (filename, order) in TABLES.items():
            columns = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            cursor = con.execute(f"SELECT * FROM {table} ORDER BY {order}")
            rows = cursor.fetchall()
            path = output / filename
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, lineterminator="\n")
                writer.writerow(columns)
                writer.writerows([[encode(v) for v in row] for row in rows])
            files[filename] = {"rows": len(rows), "sha256": checksum(path)}
        indicators = con.execute("SELECT indicator_code,frequency FROM indicators ORDER BY indicator_code").fetchall()
        for indicator, frequency in indicators:
            if not re.fullmatch(r"[a-z0-9_]+", indicator):
                raise ValueError(f"Unsafe indicator code for filename: {indicator!r}")
            columns = [r[1] for r in con.execute("PRAGMA table_info(observations)")]
            cursor = con.execute("SELECT * FROM observations WHERE indicator_code=? ORDER BY country_code,period,source_series_code", (indicator,))
            rows = cursor.fetchall()
            probe = io.StringIO(newline="")
            writer = csv.writer(probe, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows([[encode(v) for v in row] for row in rows])
            if probe.tell() <= MAX_PARTITION_BYTES:
                partitions = [(f"{indicator}.csv", rows)]
            else:
                groups = {}
                for row in rows:
                    year = int(row[2][:4]); start = (year // 5) * 5
                    groups.setdefault(start, []).append(row)
                partitions = [(f"{indicator}_{start}_{start+4}.csv", groups[start]) for start in sorted(groups)]
                refined = []
                for name, group in partitions:
                    check = io.StringIO(newline="")
                    check_writer = csv.writer(check, lineterminator="\n")
                    check_writer.writerow(columns)
                    check_writer.writerows([[encode(v) for v in row] for row in group])
                    if check.tell() <= MAX_PARTITION_BYTES:
                        refined.append((name, group))
                    else:
                        years={}
                        for row in group: years.setdefault(int(row[2][:4]),[]).append(row)
                        refined.extend((f"{indicator}_{year}_{year}.csv",years[year]) for year in sorted(years))
                partitions=refined
                oversized=[]
                for name,group in partitions:
                    check=io.StringIO(newline=""); w=csv.writer(check,lineterminator="\n"); w.writerow(columns); w.writerows([[encode(v) for v in row] for row in group])
                    if check.tell()>MAX_PARTITION_BYTES: oversized.append(name)
                if oversized: raise ValueError(f"Annual partition still exceeds {MAX_PARTITION_BYTES} bytes: {oversized}")
            for filename, group in partitions:
                path = output / "observations" / frequency / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f, lineterminator="\n")
                    writer.writerow(columns)
                    writer.writerows([[encode(v) for v in row] for row in group])
                files[str(path.relative_to(output))] = {"rows": len(group), "sha256": checksum(path), "indicator_code": indicator, "frequency": frequency}
        metadata=dict(con.execute("SELECT key,value FROM schema_meta"))
    finally:
        con.close()
    manifest = {"format_version": 1, "database": "macroeconomic research dataset", "release": metadata.get("release_date"), "null_token": NULL, "tables": {k: v[0] for k,v in TABLES.items()}, "files": files}
    (output / "release.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export(database: Path, output: Path):
    output=output.resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=f".{output.name}-staging-",dir=output.parent))
    backup=output.with_name(f".{output.name}-previous")
    try:
        _export_into(database,stage)
        if backup.exists():
            if backup.is_dir(): shutil.rmtree(backup)
            else: backup.unlink()
        if output.exists(): os.replace(output,backup)
        try:
            os.replace(stage,output)
        except Exception:
            if backup.exists() and not output.exists(): os.replace(backup,output)
            raise
        if backup.exists(): shutil.rmtree(backup)
    except Exception:
        if stage.exists(): shutil.rmtree(stage,ignore_errors=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True,type=Path,help="SQLite database to export")
    p.add_argument("--output",required=True,type=Path,help="Source-data directory to create/update")
    args=p.parse_args(); export(args.database,args.output)


if __name__ == "__main__": main()
