#!/usr/bin/env python3
"""Read-only health and workload audit for the Economics Society SQLite release.

Uses only Python's standard library. No network access, writes, or credentials.
Scores summarize explicit checks; they are not probabilities of correctness.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import re
import shutil
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

EXPECTED = {
    "tables": {"countries", "sources", "indicators", "source_snapshots", "source_series_metadata", "observations", "schema_meta"},
    "views": {"indicator_coverage", "research_observations"},
    "indexes": {"idx_observations_country_indicator", "idx_observations_indicator_period", "idx_observations_period"},
    "counts": {"countries": 217, "indicators": 40, "observations": 263863},
    "obs_columns": {"country_code", "indicator_code", "period", "frequency", "value", "value_status", "source_id", "source_series_code", "seasonal_adjustment", "observation_metadata"},
    "research_columns": {"wb_code", "country_name", "indicator_code", "display_name", "period", "frequency", "value", "unit", "value_status", "source_id", "source_series_code"},
    "latest_csv_columns": ["country_name", "wb_code", "wb_region", "income_level", "indicator", "indicator_code", "latest_available_period", "frequency", "value", "unit", "value_status", "source_id", "source_series_code"],
    "all_csv_columns": ["serial_no", "wb_code", "country_name", "wb_region", "income_level", "indicator_code", "display_name", "period", "frequency", "value", "unit", "value_status", "seasonal_adjustment", "source_id", "source_series_code", "observation_metadata"],
}
WEIGHTS = {"integrity": 20, "schema": 12, "data_quality": 18, "relationships": 12, "coverage": 10, "retrieval": 14, "exports": 8, "performance_storage": 6}
MAX_FRACTION = re.compile(r"^\d{4}$")
QUARTER = re.compile(r"^\d{4}-Q[1-4]$")


class Audit:
    def __init__(self, db: Path, root: Path | None, timing_runs: int):
        self.db, self.root, self.timing_runs = db, root, max(1, timing_runs)
        self.results: list[dict] = []
        self.metrics: dict = {}
        self.critical_failure = False

    def check(self, area: str, name: str, ok: bool, detail: str, *, critical: bool = False, measured=None):
        self.results.append({"area": area, "name": name, "status": "pass" if ok else "fail", "critical": critical, "detail": detail, "measurement": measured})
        self.critical_failure |= critical and not ok

    def warn(self, area: str, name: str, detail: str, measured=None):
        self.results.append({"area": area, "name": name, "status": "warning", "critical": False, "detail": detail, "measurement": measured})

    def run(self):
        if not self.db.is_file():
            self.check("integrity", "database file exists", False, f"Not found: {self.db}", critical=True)
            return self.report()
        try:
            uri = self.db.resolve().as_uri() + "?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=10)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
        except Exception as exc:
            self.check("integrity", "open read-only", False, str(exc), critical=True)
            return self.report()
        try:
            self._integrity(con)
            objects = self._schema(con)
            if "observations" not in objects.get("table", set()):
                return self.report()
            self._data(con)
            self._relationships(con)
            self._coverage(con)
            self._retrieval(con)
            self._exports(con)
            self._performance(con)
            self._storage(con)
        except Exception as exc:
            self.check("integrity", "audit completed", False, f"Unexpected audit error: {type(exc).__name__}: {exc}", critical=True)
        finally:
            con.close()
        return self.report()

    def _integrity(self, con):
        checks = con.execute("PRAGMA integrity_check").fetchall()
        ok = len(checks) == 1 and checks[0][0] == "ok"
        self.check("integrity", "SQLite integrity_check", ok, checks[0][0] if checks else "No result", critical=True)
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        self.check("integrity", "foreign_key_check", not fk, f"{len(fk)} foreign-key violation(s)", critical=True, measured=len(fk))
        self.metrics["foreign_key_violations"] = len(fk)

    def _schema(self, con):
        rows = con.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        objects = {}
        for row in rows:
            objects.setdefault(row["type"], set()).add(row["name"])
        for typ, key in (("table", "tables"), ("view", "views"), ("index", "indexes")):
            missing = EXPECTED[key] - objects.get(typ, set())
            self.check("schema", f"required {typ}s", not missing, "All expected objects present" if not missing else "Missing: " + ", ".join(sorted(missing)), critical=typ == "table" and "observations" in missing)
        for table, cols in (("observations", EXPECTED["obs_columns"]), ("research_observations", EXPECTED["research_columns"])):
            if table not in objects.get("table" if table == "observations" else "view", set()):
                continue
            actual = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            missing = cols - actual
            self.check("schema", f"{table} columns", not missing, "Required columns present" if not missing else "Missing: " + ", ".join(sorted(missing)))
        return objects

    def _data(self, con):
        counts = {}
        for table, expected in EXPECTED["counts"].items():
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            counts[table] = n
            floor = int(expected * 0.95)
            self.check("data_quality", f"{table} baseline count", n >= floor, f"{n:,} rows; release baseline {expected:,}, warning threshold {floor:,}", critical=table == "observations" and n == 0, measured=n)
        self.metrics["row_counts"] = counts
        nonfinite = con.execute("SELECT COUNT(*) FROM observations WHERE value IS NULL OR value != value OR abs(value) > 1.0e300").fetchone()[0]
        self.check("data_quality", "finite non-null observation values", nonfinite == 0, f"{nonfinite} invalid value(s)", measured=nonfinite)
        bad_freq = con.execute("SELECT COUNT(*) FROM observations WHERE frequency NOT IN ('annual','quarterly') OR frequency != (SELECT frequency FROM indicators WHERE indicators.indicator_code=observations.indicator_code)").fetchone()[0]
        self.check("data_quality", "frequency matches indicator", bad_freq == 0, f"{bad_freq} mismatched/unsupported row(s)", measured=bad_freq)
        bad_period = con.execute("SELECT COUNT(*) FROM observations WHERE (frequency='annual' AND (length(period)!=4 OR period GLOB '*[^0-9]*')) OR (frequency='quarterly' AND (length(period)!=7 OR substr(period,6,2) NOT IN ('Q1','Q2','Q3','Q4') OR substr(period,1,4) GLOB '*[^0-9]*'))").fetchone()[0]
        self.check("data_quality", "period labels valid", bad_period == 0, f"{bad_period} invalid period(s)", measured=bad_period)
        invalid_json = con.execute("SELECT COUNT(*) FROM observations WHERE observation_metadata IS NOT NULL AND json_valid(observation_metadata)=0").fetchone()[0]
        self.check("data_quality", "observation metadata JSON", invalid_json == 0, f"{invalid_json} invalid JSON value(s)", measured=invalid_json)
        bad_status = con.execute("SELECT COUNT(*) FROM observations WHERE value_status NOT IN ('observed','estimated','derived','forecast','provisional')").fetchone()[0]
        self.check("data_quality", "observation status domain", bad_status == 0, f"{bad_status} unsupported status(es)", measured=bad_status)

    def _relationships(self, con):
        orphan = con.execute("SELECT COUNT(*) FROM observations o LEFT JOIN countries c ON c.wb_code=o.country_code LEFT JOIN indicators i ON i.indicator_code=o.indicator_code LEFT JOIN sources s ON s.source_id=o.source_id WHERE c.wb_code IS NULL OR i.indicator_code IS NULL OR s.source_id IS NULL").fetchone()[0]
        self.check("relationships", "observation country/indicator/source links", orphan == 0, f"{orphan} orphaned observation(s)", critical=orphan > 0, measured=orphan)
        dup = con.execute("SELECT COUNT(*) FROM (SELECT country_code,indicator_code,period,source_series_code FROM observations GROUP BY 1,2,3,4 HAVING COUNT(*)>1)").fetchone()[0]
        self.check("relationships", "observation logical key uniqueness", dup == 0, f"{dup} duplicate key group(s)", measured=dup)
        orphan_metadata = con.execute("SELECT COUNT(*) FROM source_series_metadata m WHERE NOT EXISTS (SELECT 1 FROM observations o WHERE o.country_code=m.country_code AND o.indicator_code=m.indicator_code AND o.source_series_code=m.source_series_code)").fetchone()[0]
        invalid_series_json = con.execute("SELECT COUNT(*) FROM source_series_metadata WHERE json_valid(series_metadata)=0").fetchone()[0]
        self.check("relationships", "source-series metadata is linked and valid", orphan_metadata == 0 and invalid_series_json == 0, f"{orphan_metadata} metadata row(s) without observations; {invalid_series_json} invalid JSON row(s)", measured={"orphan_metadata":orphan_metadata,"invalid_json":invalid_series_json})

    def _coverage(self, con):
        rows = con.execute("SELECT i.indicator_code,i.frequency,COUNT(o.period) n,MIN(o.period) first_period,MAX(o.period) last_period FROM indicators i LEFT JOIN observations o USING(indicator_code) GROUP BY i.indicator_code,i.frequency ORDER BY i.indicator_code").fetchall()
        empty = [r["indicator_code"] for r in rows if not r["n"]]
        unknown = [r["indicator_code"] for r in rows if r["frequency"] not in ("annual", "quarterly")]
        coverage = [{"indicator":r["indicator_code"],"frequency":r["frequency"],"observations":r["n"],"first_period":r["first_period"],"last_period":r["last_period"]} for r in rows]
        self.metrics["indicator_coverage"] = coverage
        self.check("coverage", "all released indicators have observations", not empty, "All indicators populated" if not empty else "Empty: " + ", ".join(empty), measured=len(empty))
        self.check("coverage", "supported indicator frequencies", not unknown, "Annual/quarterly only" if not unknown else "Unexpected: " + ", ".join(unknown), measured=len(unknown))
        view_mismatch = con.execute("SELECT COUNT(*) FROM (SELECT indicator_code,frequency,COUNT(*) n,MIN(period) first_period,MAX(period) last_period FROM observations GROUP BY 1,2 EXCEPT SELECT indicator_code,frequency,observation_count,first_period,last_period FROM indicator_coverage)").fetchone()[0]
        self.check("coverage", "coverage view agrees with observations", view_mismatch == 0, f"{view_mismatch} unmatched coverage group(s)", measured=view_mismatch)

    def _timed(self, con, sql, params=()):
        times=[]
        for _ in range(self.timing_runs):
            start=time.perf_counter(); cur=con.execute(sql,params); cur.fetchall(); times.append((time.perf_counter()-start)*1000)
        return round(statistics.median(times), 3)

    def _retrieval(self, con):
        look=con.execute("SELECT country_name,wb_code FROM countries WHERE wb_code='IND'").fetchone()
        self.check("retrieval", "country lookup by code", bool(look and look["country_name"]), f"India code lookup {'returned '+look['country_name'] if look else 'returned no row'}", critical=look is None)
        hist=con.execute("SELECT period,value FROM observations WHERE country_code='IND' AND indicator_code='gdp_real_growth_yoy_pct_quarterly' ORDER BY period").fetchall()
        periods=[r["period"] for r in hist]
        self.check("retrieval", "country-indicator history", len(hist)>0 and periods==sorted(periods), f"{len(hist)} rows; ordered periods; range {periods[0] if periods else 'N/A'} to {periods[-1] if periods else 'N/A'}", critical=not hist, measured=len(hist))
        joined=con.execute("SELECT country_name,display_name,period,value FROM research_observations WHERE wb_code='IND' AND indicator_code='gdp_real_growth_yoy_pct_quarterly' ORDER BY period").fetchall()
        self.check("retrieval", "joined research view lookup", len(joined)==len(hist) and bool(joined and joined[0]["country_name"] and joined[0]["display_name"]), f"{len(joined)} joined rows; {'matches' if len(joined)==len(hist) else 'does not match'} direct history", critical=not joined, measured=len(joined))
        latest=con.execute("SELECT wb_code,indicator_code,period FROM (SELECT wb_code,indicator_code,period,ROW_NUMBER() OVER(PARTITION BY wb_code,indicator_code ORDER BY period DESC) rn FROM research_observations) WHERE rn=1").fetchall()
        expected=con.execute("SELECT COUNT(*) FROM (SELECT country_code,indicator_code FROM observations GROUP BY 1,2)").fetchone()[0]
        self.check("retrieval", "latest-per-country-and-indicator recall", len(latest)==expected and all(QUARTER.fullmatch(r["period"]) or MAX_FRACTION.fullmatch(r["period"]) for r in latest), f"{len(latest):,} returned; expected {expected:,} country-indicator pairs", measured=len(latest))
        top=con.execute("SELECT country_name,value FROM research_observations WHERE indicator_code='population_total_annual' AND period=(SELECT MAX(period) FROM observations WHERE indicator_code='population_total_annual') ORDER BY value DESC LIMIT 10").fetchall()
        self.check("retrieval", "ranked latest-period query", len(top)==10 and all(top[i]["value"]>=top[i+1]["value"] for i in range(len(top)-1)), f"Returned {len(top)} rows in descending value order", measured=len(top))
        self.metrics["retrieval_sample"]={"india_quarterly_growth_rows":len(hist),"joined_rows":len(joined),"latest_country_indicator_pairs":len(latest),"latest_pair_expected":expected,"top_population_rows":len(top)}

    def _exports(self, con):
        if not self.root:
            self.warn("exports", "CSV companion parity", "No repository root supplied; use --root to check published CSV files")
            return
        latest=self.root/"macro_research_latest.csv"; all_csv=self.root/"macro_research_all_observations.csv.gz"
        expected_latest=con.execute("SELECT COUNT(*) FROM (SELECT country_code,indicator_code FROM observations GROUP BY 1,2)").fetchone()[0]
        expected_all=con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        for path,expected,headers,label in ((latest,expected_latest,EXPECTED["latest_csv_columns"],"latest CSV"),(all_csv,expected_all,EXPECTED["all_csv_columns"],"full-history CSV")):
            try:
                op=gzip.open if path.suffix==".gz" else open
                with op(path,"rt",encoding="utf-8-sig",newline="") as f:
                    reader=csv.reader(f); actual=next(reader); n=sum(1 for _ in reader)
                ok=actual==headers and n==expected
                self.check("exports",f"{label} readable and matches database",ok,f"{n:,} rows (expected {expected:,}); {'headers match' if actual==headers else 'headers differ'}",critical=label=="full-history CSV" and not path.exists(),measured={"rows":n,"expected_rows":expected,"headers_match":actual==headers})
            except Exception as exc:
                self.check("exports",f"{label} readable and matches database",False,f"{type(exc).__name__}: {exc}",critical=label=="full-history CSV")

    def _performance(self, con):
        samples={
            "country_indicator_history_ms":("SELECT period,value FROM observations WHERE country_code='IND' AND indicator_code='gdp_real_growth_yoy_pct_quarterly' ORDER BY period",()),
            "latest_by_indicator_ms":("SELECT wb_code,country_name,value FROM research_observations WHERE indicator_code='population_total_annual' AND period=(SELECT MAX(period) FROM observations WHERE indicator_code='population_total_annual') ORDER BY value DESC LIMIT 100",()),
            "coverage_view_ms":("SELECT * FROM indicator_coverage ORDER BY frequency,indicator_code",()),
        }
        timings={k:self._timed(con,*v) for k,v in samples.items()}
        plans={
            "country_indicator_history":con.execute("EXPLAIN QUERY PLAN SELECT value FROM observations WHERE country_code='IND' AND indicator_code='gdp_real_growth_yoy_pct_quarterly' ORDER BY period").fetchall(),
            "latest_by_indicator":con.execute("EXPLAIN QUERY PLAN SELECT value FROM observations WHERE indicator_code='population_total_annual' AND period=(SELECT MAX(period) FROM observations WHERE indicator_code='population_total_annual')").fetchall(),
        }
        plan_text={name:" | ".join(str(tuple(r)) for r in rows) for name,rows in plans.items()}
        indexed={name:"USING INDEX" in p or "USING COVERING INDEX" in p for name,p in plan_text.items()}
        for name,ok in indexed.items(): self.check("performance_storage",f"{name} uses an index",ok,plan_text[name])
        self.metrics["query_median_ms"]=timings
        self.metrics["query_plans"]=plan_text
        self.warn("performance_storage","query timing context","Timings are descriptive and hardware-dependent; no universal speed threshold is applied",timings)

    def _storage(self, con):
        page_size=con.execute("PRAGMA page_size").fetchone()[0]
        pages=con.execute("PRAGMA page_count").fetchone()[0]
        free=con.execute("PRAGMA freelist_count").fetchone()[0]
        db_bytes=self.db.stat().st_size
        self.metrics["storage"]={"file_bytes":db_bytes,"page_size":page_size,"page_count":pages,"allocated_bytes":page_size*pages,"free_pages":free,"free_page_percent":round(100*free/pages,2) if pages else 0}
        self.check("performance_storage","SQLite page accounting",page_size>0 and pages>0 and free<=pages,f"{pages:,} pages × {page_size:,} bytes; {free:,} free pages",measured=self.metrics["storage"])
        self.check("performance_storage","freelist/bloat estimate",pages>0 and free/pages<=0.20,f"{(100*free/pages if pages else 0):.2f}% free pages (warning threshold 20%)",measured=round(100*free/pages,2) if pages else 0)

    def report(self):
        areas={}
        for area in WEIGHTS:
            rs=[r for r in self.results if r["area"]==area and r["status"] in ("pass","fail")]
            passed=sum(r["status"]=="pass" for r in rs)
            areas[area]={"score":round(100*passed/len(rs),1) if rs else None,"passed":passed,"failed":len(rs)-passed,"checks":len(rs),"weight":WEIGHTS[area]}
        included=[(v["score"],v["weight"]) for v in areas.values() if v["score"] is not None]
        overall=round(sum(score*weight for score,weight in included)/sum(weight for _,weight in included),1) if included else 0
        if self.critical_failure: overall=min(overall,49.9)
        return {"audit_version":"1.0","generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),"database":str(self.db.resolve()),"database_bytes":self.db.stat().st_size if self.db.exists() else None,"overall_score":overall,"rating":"critical" if self.critical_failure else "healthy" if overall>=90 else "needs_attention" if overall>=70 else "poor","score_note":"Weighted percentage of explicit checks passed; not a probability that data are correct. Timing checks are descriptive, not scored.","critical_failure":self.critical_failure,"areas":areas,"summary":{"passed":sum(r["status"]=="pass" for r in self.results),"failed":sum(r["status"]=="fail" for r in self.results),"warnings":sum(r["status"]=="warning" for r in self.results)},"checks":self.results,"metrics":self.metrics}


def prepare_db(args):
    if args.database:
        return Path(args.database), Path(args.root) if args.root else None
    root=Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    parts=[root/f"macro_research.sqlite.gz.part{i:02d}" for i in range(3)]
    if not all(p.is_file() for p in parts):
        raise FileNotFoundError("Supply --database or provide all three archive parts in --root")
    temp=Path(tempfile.mkdtemp(prefix="macro-db-health-"))
    gz=temp/"snapshot.sqlite.gz"; db=temp/"snapshot.sqlite"
    with gz.open("wb") as out:
        for part in parts:
            with part.open("rb") as src: shutil.copyfileobj(src,out)
    with gzip.open(gz,"rb") as src,db.open("wb") as out: shutil.copyfileobj(src,out)
    return db,root


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",help="Audit an extracted SQLite file (read-only)")
    p.add_argument("--root",help="Folder containing the three archive parts and CSV exports")
    p.add_argument("--json",dest="json_path",help="Also write the complete JSON report to this path")
    p.add_argument("--timing-runs",type=int,default=3,help="Runs per representative read query (default: 3)")
    p.add_argument("--compact",action="store_true",help="Print a concise category summary")
    args=p.parse_args()
    temp=None
    try:
        db,root=prepare_db(args)
        if not args.database: temp=db.parent
        report=Audit(db,root,args.timing_runs).run()
        if args.json_path: Path(args.json_path).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        if args.compact:
            print(f"Database health: {report['overall_score']:.1f}% ({report['rating']})")
            for name,a in report["areas"].items(): print(f"  {name:22} {a['score'] if a['score'] is not None else 'N/A'}%  ({a['passed']}/{a['checks']} checks)")
            print(f"Checks: {report['summary']['passed']} passed, {report['summary']['failed']} failed, {report['summary']['warnings']} warnings")
            for c in report["checks"]:
                if c["status"]!="pass": print(f"{c['status'].upper():7} {c['area']}: {c['name']} — {c['detail']}")
        else: print(json.dumps(report,indent=2))
        return 2 if report["critical_failure"] else 1 if report["summary"]["failed"] else 0
    except Exception as exc:
        print(f"Audit could not run: {type(exc).__name__}: {exc}")
        return 2
    finally:
        if temp:
            shutil.rmtree(temp,ignore_errors=True)


if __name__=="__main__":
    raise SystemExit(main())
