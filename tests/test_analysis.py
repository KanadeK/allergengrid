from __future__ import annotations

import unittest
from pathlib import Path

from allergengrid.analysis import analyze_case
from allergengrid.loader import load_case
from allergengrid.models import Severity, Status

ROOT = Path(__file__).resolve().parents[1]
SAFE_CASE = ROOT / "examples" / "community-supper-safe"
RISKY_CASE = ROOT / "examples" / "community-supper-risky"


class AnalysisTests(unittest.TestCase):
    def test_safe_case_has_expected_action_statuses(self) -> None:
        result = analyze_case(load_case(SAFE_CASE))

        self.assertEqual(
            result.assessment_for("maya", "herb-rice").status,
            Status.CANDIDATE,
        )
        self.assertEqual(
            result.assessment_for("maya", "yogurt-dip").status,
            Status.HOLD,
        )
        self.assertEqual(
            result.assessment_for("leo", "yogurt-dip").status,
            Status.BLOCK,
        )
        self.assertFalse(result.has_errors)
        self.assertFalse(result.has_warnings)

    def test_direct_conflict_reason_is_traceable(self) -> None:
        result = analyze_case(load_case(SAFE_CASE))
        assessment = result.assessment_for("leo", "yogurt-dip")

        self.assertEqual(assessment.status, Status.BLOCK)
        self.assertEqual(assessment.reasons[0].code, "DIRECT_CONTAINS")
        self.assertEqual(assessment.reasons[0].allergens, ("milk",))

    def test_shared_board_propagates_declared_allergens(self) -> None:
        result = analyze_case(load_case(RISKY_CASE))
        assessment = result.assessment_for("ava", "fruit-cup")

        self.assertEqual(assessment.status, Status.HOLD)
        self.assertTrue(any(reason.code == "PREP_CONTAINS" for reason in assessment.reasons))
        self.assertTrue(any(reason.resource == "board-a" for reason in assessment.reasons))

    def test_risky_case_invalidates_free_from_claim(self) -> None:
        result = analyze_case(load_case(RISKY_CASE))
        errors = [finding for finding in result.findings if finding.severity is Severity.ERROR]

        self.assertTrue(any(finding.code == "AG203" for finding in errors))
        self.assertTrue(result.has_errors)


if __name__ == "__main__":
    unittest.main()
