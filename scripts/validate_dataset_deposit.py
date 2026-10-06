#!/usr/bin/env python3
"""Validate the structure and basic file integrity of changed dataset deposits."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = ("README.md", "metadata.yml", "codebook.csv")
CODEBOOK_COLUMNS = {
    "variable_name", "label", "definition", "unit", "frequency",
    "geography", "source", "construction", "missing_value_codes", "notes",
}


class ValidationError(Exception):
    pass


def changed_dataset_ids(base_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=ROOT, check=True, text=True, capture_output=True,
    )
    ids = set()
    for name in result.stdout.splitlines():
        parts = Path(name).parts
        if len(parts) >= 3 and parts[0] == "datasets" and parts[1] != "macroeconomic-indicators":
            ids.add(parts[1])
    return sorted(ids)


def check_csv(path: Path, *, require_rows: bool) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if not header or any(not name.strip() for name in header):
                raise ValidationError(f"{path.relative_to(ROOT)}: missing or blank CSV header")
            if len(set(header)) != len(header):
                raise ValidationError(f"{path.relative_to(ROOT)}: duplicate CSV column names")
            rows = 0
            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    raise ValidationError(
                        f"{path.relative_to(ROOT)}:{line_number}: expected {len(header)} fields, got {len(row)}"
                    )
                rows += 1
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: cannot read valid UTF-8 CSV: {exc}") from exc
    if require_rows and rows == 0:
        raise ValidationError(f"{path.relative_to(ROOT)}: no data rows")
    return rows


def validate_dataset(dataset_id: str) -> list[str]:
    folder = ROOT / "datasets" / dataset_id
    if not folder.is_dir():
        return [f"SKIP {dataset_id}: folder was removed in this change"]
    problems = []
    for filename in REQUIRED_FILES:
        if not (folder / filename).is_file():
            problems.append(f"{dataset_id}: required file missing: {filename}")

    metadata_path = folder / "metadata.yml"
    if metadata_path.is_file():
        try:
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            problems.append(f"{dataset_id}: metadata.yml is not valid UTF-8 YAML: {exc}")
            metadata = None
        if not isinstance(metadata, dict):
            problems.append(f"{dataset_id}: metadata.yml must contain a YAML mapping")
        else:
            for key in ("dataset_id", "title", "description", "license", "citation"):
                if not isinstance(metadata.get(key), str) or not metadata[key].strip():
                    problems.append(f"{dataset_id}: metadata field '{key}' must be a non-empty string")
            if metadata.get("dataset_id") != dataset_id:
                problems.append(f"{dataset_id}: metadata dataset_id must match the folder name")
            if metadata.get("access_level") != "public":
                problems.append(f"{dataset_id}: access_level must be 'public' for this repository")
            if metadata.get("consent_or_permissions_reviewed") is not True:
                problems.append(f"{dataset_id}: consent_or_permissions_reviewed must be true")
            for key in ("authors", "sources"):
                if not isinstance(metadata.get(key), list) or not metadata[key]:
                    problems.append(f"{dataset_id}: metadata field '{key}' must be a non-empty list")
            transforms = metadata.get("transformations", [])
            if transforms and (not (folder / "scripts").is_dir() or not any(p.is_file() for p in (folder / "scripts").rglob("*"))):
                problems.append(f"{dataset_id}: transformations are listed but scripts/ is empty or missing")
            if transforms and (not (folder / "tests").is_dir() or not list((folder / "tests").glob("test_*.py"))):
                problems.append(f"{dataset_id}: transformed data need at least one tests/test_*.py file")
            release_date = metadata.get("release_date")
            if release_date:
                try:
                    dt.date.fromisoformat(str(release_date))
                except ValueError:
                    problems.append(f"{dataset_id}: release_date must use YYYY-MM-DD")

    codebook = folder / "codebook.csv"
    if codebook.is_file():
        try:
            with codebook.open("r", encoding="utf-8-sig", newline="") as stream:
                header = next(csv.reader(stream, strict=True), None)
            missing = CODEBOOK_COLUMNS - set(header or [])
            if missing:
                problems.append(f"{dataset_id}: codebook.csv missing columns: {', '.join(sorted(missing))}")
            rows = check_csv(codebook, require_rows=True)
            if rows == 0:
                problems.append(f"{dataset_id}: codebook.csv must document at least one variable")
        except (OSError, UnicodeDecodeError, csv.Error, ValidationError) as exc:
            problems.append(str(exc))

    data_files = sorted((folder / "data").rglob("*.csv")) if (folder / "data").is_dir() else []
    if not data_files:
        problems.append(f"{dataset_id}: add at least one CSV file under data/")
    for path in data_files:
        try:
            check_csv(path, require_rows=True)
        except (OSError, ValidationError) as exc:
            problems.append(str(exc))

    if problems:
        return [f"FAIL {problem}" for problem in problems]
    return [f"PASS {dataset_id}: metadata, docs, codebook, and {len(data_files)} CSV file(s) validated"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Fetched base branch, e.g. origin/main")
    args = parser.parse_args()
    try:
        ids = changed_dataset_ids(args.base)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr, file=sys.stderr)
        return 2
    if not ids:
        print("No dataset deposit folders changed; deposit checks skipped.")
        return 0
    print(f"Checking changed dataset folder(s): {', '.join(ids)}")
    results = [message for dataset_id in ids for message in validate_dataset(dataset_id)]
    print("\n".join(results))
    return int(any(message.startswith("FAIL ") for message in results))


if __name__ == "__main__":
    raise SystemExit(main())
