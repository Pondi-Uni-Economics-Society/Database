"""Tests for the public dataset deposit validator."""
from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("validate_dataset_deposit.py")
SPEC = importlib.util.spec_from_file_location("validate_dataset_deposit", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


class DepositValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        validator.ROOT = Path(self.temp.name)
        self.folder = validator.ROOT / "datasets" / "sample-study"
        (self.folder / "data").mkdir(parents=True)
        (self.folder / "README.md").write_text("# Sample\n", encoding="utf-8")
        (self.folder / "metadata.yml").write_text(
            "dataset_id: sample-study\ntitle: Sample\ndescription: Sample data\n"
            "license: CC0-1.0\ncitation: Sample citation\naccess_level: public\n"
            "consent_or_permissions_reviewed: true\nauthors: [Member]\nsources: [Publisher]\n"
            "transformations: []\nrelease_date: '2026-01-15'\n",
            encoding="utf-8",
        )
        with (self.folder / "codebook.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(sorted(validator.CODEBOOK_COLUMNS))
            writer.writerow(["income", "Income", "Annual income", "USD", "annual", "India", "Survey", "", "NA", ""])
        with (self.folder / "data" / "observations.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["person_code", "income"])
            writer.writerow(["P001", "100"])

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_public_deposit_passes(self):
        result = validator.validate_dataset("sample-study")
        self.assertTrue(result[0].startswith("PASS "), result)

    def test_restricted_access_is_rejected(self):
        metadata = self.folder / "metadata.yml"
        metadata.write_text(metadata.read_text(encoding="utf-8").replace("access_level: public", "access_level: restricted"), encoding="utf-8")
        result = validator.validate_dataset("sample-study")
        self.assertTrue(any("access_level must be 'public'" in item for item in result), result)

    def test_malformed_csv_is_rejected(self):
        (self.folder / "data" / "observations.csv").write_text("a,b\n1\n", encoding="utf-8")
        result = validator.validate_dataset("sample-study")
        self.assertTrue(any("expected 2 fields, got 1" in item for item in result), result)


if __name__ == "__main__":
    unittest.main()

