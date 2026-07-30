from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from allergengrid.loader import InputError, load_case

ROOT = Path(__file__).resolve().parents[1]
SAFE_CASE = ROOT / "examples" / "community-supper-safe"


class LoaderTests(unittest.TestCase):
    def copy_case(self, temporary: str) -> Path:
        case = Path(temporary) / "case"
        shutil.copytree(SAFE_CASE, case)
        return case

    def test_loads_complete_case_and_hashes_inputs(self) -> None:
        loaded = load_case(SAFE_CASE)

        self.assertEqual(loaded.event.profile, "us")
        self.assertEqual(len(loaded.event.dishes), 3)
        self.assertEqual(len(loaded.guests), 3)
        self.assertEqual(set(loaded.input_hashes), {"event.json", "guests.csv"})
        self.assertEqual(len(loaded.input_digest), 64)

    def test_rejects_unknown_allergen_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            event_path = case / "event.json"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["dishes"][0]["ingredients"][0]["contains"] = ["dragon-fruit-dust"]
            event_path.write_text(json.dumps(event), encoding="utf-8")

            with self.assertRaisesRegex(InputError, "unknown allergen"):
                load_case(case)

    def test_normalizes_declared_aliases_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            event_path = case / "event.json"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["dishes"][2]["ingredients"][0]["contains"] = ["eggs"]
            event_path.write_text(json.dumps(event), encoding="utf-8")

            loaded = load_case(case)

        self.assertIn("egg", loaded.event.dishes[2].contains)

    def test_rejects_missing_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)
            (case / "event.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(InputError, "guests.csv"):
                load_case(case)

    def test_rejects_invalid_json_and_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            (case / "event.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(InputError, "invalid JSON"):
                load_case(case)

            (case / "event.json").write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(InputError, "expected UTF-8"):
                load_case(case)

    def test_rejects_wrong_root_schema_and_profile(self) -> None:
        mutations = [
            ([], "expected an object"),
            ({"schema_version": 2}, "schema version 1"),
        ]
        for event, expected in mutations:
            with (
                self.subTest(expected=expected),
                tempfile.TemporaryDirectory() as temporary,
            ):
                case = self.copy_case(temporary)
                (case / "event.json").write_text(json.dumps(event), encoding="utf-8")
                with self.assertRaisesRegex(InputError, expected):
                    load_case(case)

        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            event_path = case / "event.json"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["profile"] = "mars"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with self.assertRaisesRegex(InputError, "must be one of"):
                load_case(case)

    def test_rejects_custom_allergen_collision_and_duplicate_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            event_path = case / "event.json"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["custom_allergens"] = [{"id": "milk", "label": "Duplicate milk"}]
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with self.assertRaisesRegex(InputError, "cannot be redeclared"):
                load_case(case)

        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            event_path = case / "event.json"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["dishes"][0]["ingredients"][0]["contains"] = [
                "tree nuts",
                "tree_nuts",
            ]
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with self.assertRaisesRegex(InputError, "alias normalization"):
                load_case(case)

    def test_rejects_bad_guest_headers_and_empty_guest_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            (case / "guests.csv").write_text("guest_id,name\none,One\n", encoding="utf-8")
            with self.assertRaisesRegex(InputError, "missing columns"):
                load_case(case)

        with tempfile.TemporaryDirectory() as temporary:
            case = self.copy_case(temporary)
            (case / "guests.csv").write_text(
                "guest_id,name,avoid_allergens,required_diets,notes\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(InputError, "at least one guest"):
                load_case(case)


if __name__ == "__main__":
    unittest.main()
