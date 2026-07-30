"""Exercise the public workflow against committed, deterministic fixtures."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from allergengrid.analysis import analyze_case
from allergengrid.bundle import create_package, verify_package
from allergengrid.loader import load_case
from allergengrid.reports import build_outputs

ROOT = Path(__file__).resolve().parents[1]
SAFE_CASE = ROOT / "examples" / "community-supper-safe"
RISKY_CASE = ROOT / "examples" / "community-supper-risky"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=Path)
    arguments = parser.parse_args()

    if arguments.keep:
        output_root = arguments.keep.resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        temporary_context = None
    else:
        temporary_context = tempfile.TemporaryDirectory(prefix="allergengrid-demo-")
        output_root = Path(temporary_context.name)
    try:
        safe = analyze_case(load_case(SAFE_CASE))
        if safe.has_errors or safe.has_warnings:
            raise RuntimeError("safe fixture unexpectedly produced findings")
        report_paths = build_outputs(safe, output_root / "report")
        _, package = create_package(SAFE_CASE, output_root / "community-supper.zip")
        verification = verify_package(package)
        if not verification.ok:
            raise RuntimeError("; ".join(verification.errors))

        risky = analyze_case(load_case(RISKY_CASE))
        if not risky.has_errors or not risky.has_warnings:
            raise RuntimeError("risky fixture did not exercise both error and warning paths")

        print(
            "SAFE: "
            f"{safe.status_counts} | report={report_paths['report.html']} | "
            f"package_entries={verification.checked_entries}"
        )
        print(
            "RISKY: "
            f"{len(risky.findings)} findings | "
            f"codes={','.join(sorted({finding.code for finding in risky.findings}))}"
        )
        return 0
    finally:
        if temporary_context is not None:
            temporary_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
