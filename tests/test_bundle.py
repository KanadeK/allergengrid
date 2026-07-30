from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from allergengrid.analysis import analyze_case
from allergengrid.bundle import create_package, verify_package
from allergengrid.loader import load_case
from allergengrid.reports import build_outputs

ROOT = Path(__file__).resolve().parents[1]
SAFE_CASE = ROOT / "examples" / "community-supper-safe"


class BundleTests(unittest.TestCase):
    def test_build_writes_complete_report_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            paths = build_outputs(analyze_case(load_case(SAFE_CASE)), output)

            self.assertEqual(
                set(paths),
                {
                    "analysis.json",
                    "kitchen-plan.md",
                    "labels.html",
                    "matrix.csv",
                    "report.html",
                    "receipt.json",
                    "manifest.sha256",
                },
            )
            report = paths["report.html"].read_text(encoding="utf-8")
            self.assertIn("Riverside community supper", report)
            self.assertIn("CANDIDATE never means medically safe", report)

    def test_csv_neutralizes_formula_shaped_guest_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / "case"
            shutil.copytree(SAFE_CASE, case)
            rows: list[list[str]] = []
            with (case / "guests.csv").open("r", encoding="utf-8", newline="") as handle:
                rows.extend(csv.reader(handle))
            rows[1][1] = '=HYPERLINK("https://example.invalid")'
            with (case / "guests.csv").open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle, lineterminator="\n").writerows(rows)
            output = Path(temporary) / "report"

            paths = build_outputs(analyze_case(load_case(case)), output)
            matrix = paths["matrix.csv"].read_text(encoding="utf-8-sig")

        self.assertIn("'=HYPERLINK", matrix)

    def test_package_is_reproducible_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.zip"
            second = Path(temporary) / "second.zip"
            create_package(SAFE_CASE, first)
            create_package(SAFE_CASE, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            verification = verify_package(first)
            self.assertTrue(verification.ok, verification.errors)
            self.assertGreater(verification.checked_entries, 5)

    def test_package_rejects_duplicate_tampered_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "case.zip"
            create_package(SAFE_CASE, package)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(package, "a") as archive:
                    archive.writestr("inputs/guests.csv", b"tampered")

            verification = verify_package(package)

        self.assertFalse(verification.ok)
        self.assertTrue(any("duplicate entry" in error for error in verification.errors))

    def test_verifier_rejects_missing_and_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing.zip"
            with zipfile.ZipFile(missing, "w") as archive:
                archive.writestr("inputs/event.json", "{}")
            self.assertFalse(verify_package(missing).ok)

            invalid = Path(temporary) / "invalid.zip"
            with zipfile.ZipFile(invalid, "w") as archive:
                archive.writestr("package-manifest.json", "{")
            verification = verify_package(invalid)

        self.assertFalse(verification.ok)
        self.assertTrue(any("invalid package manifest" in item for item in verification.errors))

    def test_verifier_reports_hash_size_missing_extra_and_unsafe_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "broken.zip"
            manifest = {
                "schema_version": 1,
                "entries": {
                    "wanted.txt": {"sha256": "0" * 64, "size": 99},
                    "missing.txt": {"sha256": "0" * 64, "size": 0},
                },
            }
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("package-manifest.json", json.dumps(manifest))
                archive.writestr("wanted.txt", "actual")
                archive.writestr("extra.txt", "extra")
                archive.writestr("../unsafe.txt", "unsafe")

            verification = verify_package(package)

        joined = "\n".join(verification.errors)
        self.assertFalse(verification.ok)
        self.assertIn("unsafe entry names", joined)
        self.assertIn("missing entries", joined)
        self.assertIn("unlisted entries", joined)
        self.assertIn("size mismatch", joined)
        self.assertIn("SHA-256 mismatch", joined)

    def test_verifier_rejects_non_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "not.zip"
            package.write_bytes(b"not a zip")
            verification = verify_package(package)

        self.assertFalse(verification.ok)
        self.assertIn("cannot read package", verification.errors[0])


if __name__ == "__main__":
    unittest.main()
