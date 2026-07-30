from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from allergengrid.cli import EXIT_FINDINGS, EXIT_OK, run

ROOT = Path(__file__).resolve().parents[1]
SAFE_CASE = ROOT / "examples" / "community-supper-safe"
RISKY_CASE = ROOT / "examples" / "community-supper-risky"


class CliTests(unittest.TestCase):
    def call(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = run(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_strict_safe_audit_passes(self) -> None:
        code, output, _ = self.call(["audit", str(SAFE_CASE), "--strict"])

        self.assertEqual(code, EXIT_OK)
        self.assertIn("candidate", output)

    def test_strict_risky_audit_fails(self) -> None:
        code, output, _ = self.call(["audit", str(RISKY_CASE), "--strict"])

        self.assertEqual(code, EXIT_FINDINGS)
        self.assertIn("AG203", output)

    def test_pack_then_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "event.zip"
            pack_code, _, _ = self.call(["pack", str(SAFE_CASE), "--out", str(package), "--strict"])
            verify_code, output, _ = self.call(["verify-pack", str(package)])

        self.assertEqual(pack_code, EXIT_OK)
        self.assertEqual(verify_code, EXIT_OK)
        self.assertIn("PASS", output)

    def test_explain_outputs_reason_path(self) -> None:
        code, output, _ = self.call(
            [
                "explain",
                str(SAFE_CASE),
                "--guest",
                "leo",
                "--dish",
                "yogurt-dip",
            ]
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("DIRECT_CONTAINS", output)

    def test_json_validate_and_audit_are_machine_readable(self) -> None:
        validate_code, validate_output, _ = self.call(["validate", str(SAFE_CASE), "--json"])
        audit_code, audit_output, _ = self.call(["audit", str(SAFE_CASE), "--json", "--strict"])

        self.assertEqual(validate_code, EXIT_OK)
        self.assertEqual(audit_code, EXIT_OK)
        self.assertIn('"ok": true', validate_output)
        self.assertIn('"assessments"', audit_output)

    def test_build_outputs_and_strict_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            safe_code, safe_output, _ = self.call(
                ["build", str(SAFE_CASE), "--out", str(output), "--strict"]
            )
            risky_code, _, _ = self.call(
                ["build", str(RISKY_CASE), "--out", str(output), "--strict"]
            )

            self.assertTrue((output / "report.html").is_file())

        self.assertEqual(safe_code, EXIT_OK)
        self.assertIn("Wrote", safe_output)
        self.assertEqual(risky_code, EXIT_FINDINGS)

    def test_init_and_nonempty_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / "new-case"
            first_code, output, _ = self.call(["init", str(case), "--profile", "eu"])
            second_code, _, error = self.call(["init", str(case)])

            self.assertTrue((case / "event.json").is_file())
            self.assertTrue((case / "guests.csv").is_file())

        self.assertEqual(first_code, EXIT_OK)
        self.assertIn("Created", output)
        self.assertNotEqual(second_code, EXIT_OK)
        self.assertIn("non-empty", error)

    def test_verify_json_failure_and_missing_explanation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            broken = Path(temporary) / "broken.zip"
            broken.write_bytes(b"broken")
            verify_code, verify_output, _ = self.call(["verify-pack", str(broken), "--json"])
            explain_code, _, explain_error = self.call(
                [
                    "explain",
                    str(SAFE_CASE),
                    "--guest",
                    "missing",
                    "--dish",
                    "herb-rice",
                ]
            )

        self.assertEqual(verify_code, EXIT_FINDINGS)
        self.assertIn('"ok": false', verify_output)
        self.assertNotEqual(explain_code, EXIT_OK)
        self.assertIn("assessment not found", explain_error)


if __name__ == "__main__":
    unittest.main()
