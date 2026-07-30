from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from allergengrid.loader import load_case
from allergengrid.validation import validate_case

ROOT = Path(__file__).resolve().parents[1]
SAFE_CASE = ROOT / "examples" / "community-supper-safe"


class ValidationTests(unittest.TestCase):
    def test_reports_actionable_semantic_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / "case"
            shutil.copytree(SAFE_CASE, case)
            event_path = case / "event.json"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["date"] = "not-a-date"

            event["resources"][0]["cleanable"] = False
            event["resources"][0]["dedicated_to"] = "missing-dish"
            event["resources"][1]["id"] = "board-rice"
            event["resources"][1]["cleanable"] = False
            event["resources"][3]["dedicated_to"] = "herb-rice"
            event["resources"] = [
                resource for resource in event["resources"] if resource["id"] != "pot-stew"
            ]

            first_ingredient = event["dishes"][0]["ingredients"][0]
            first_ingredient["contains"] = ["peanut"]
            first_ingredient["may_contain"] = ["peanut"]
            first_ingredient["evidence"] = ""
            event["dishes"][0]["free_from"] = ["peanut"]
            event["dishes"][1]["ingredients"][0]["verified"] = False

            event["preparation"][0]["order"] = 0
            event["preparation"][2]["order"] = 0
            event["preparation"][0]["clean_before"] = [
                "board-rice",
                "board-stew",
                "missing-resource",
            ]
            event["preparation"][1]["order"] = 0
            event["preparation"] = [
                step for step in event["preparation"] if step["dish"] != "lentil-stew"
            ]
            event["preparation"].append(
                {
                    "order": 4,
                    "dish": "herb-rice",
                    "clean_before": [],
                    "note": "Duplicate dish step",
                }
            )
            event["preparation"].append(
                {
                    "order": 5,
                    "dish": "missing-dish",
                    "clean_before": [],
                    "note": "",
                }
            )
            event_path.write_text(json.dumps(event), encoding="utf-8")

            guest_path = case / "guests.csv"
            with guest_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            rows[2][0] = rows[1][0]
            with guest_path.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle, lineterminator="\n").writerows(rows)

            codes = {finding.code for finding in validate_case(load_case(case))}

        expected = {f"AG{number:03d}" for number in range(1, 19)}
        self.assertTrue(expected <= codes, codes)


if __name__ == "__main__":
    unittest.main()
