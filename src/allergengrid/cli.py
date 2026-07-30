"""AllergenGrid command-line interface."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import NoReturn

from allergengrid import __version__
from allergengrid.analysis import analyze_case
from allergengrid.bundle import create_package, verify_package
from allergengrid.loader import EVENT_FILE, GUESTS_FILE, InputError, load_case
from allergengrid.models import AnalysisResult, Finding, Severity, Status
from allergengrid.reports import analysis_data, build_outputs
from allergengrid.validation import validate_case

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_FINDINGS = 2

_SCAFFOLD_EVENT: dict[str, object] = {
    "schema_version": 1,
    "name": "Community supper",
    "date": "2026-08-15",
    "revision": "draft-1",
    "profile": "us",
    "custom_allergens": [],
    "resources": [
        {
            "id": "board-a",
            "name": "Preparation board A",
            "kind": "surface",
            "cleanable": True,
            "dedicated_to": None,
        },
        {
            "id": "spoon-rice",
            "name": "Rice serving spoon",
            "kind": "service",
            "cleanable": True,
            "dedicated_to": "herb-rice",
        },
    ],
    "dishes": [
        {
            "id": "herb-rice",
            "name": "Herb rice",
            "ingredients": [
                {
                    "name": "Rice",
                    "contains": [],
                    "may_contain": [],
                    "verified": True,
                    "evidence": "Current package label checked YYYY-MM-DD",
                },
                {
                    "name": "Fresh herbs",
                    "contains": [],
                    "may_contain": [],
                    "verified": True,
                    "evidence": "Supplier specification checked YYYY-MM-DD",
                },
            ],
            "diet_tags": ["vegan", "vegetarian"],
            "free_from": [],
            "prep_resources": ["board-a"],
            "service_resources": ["spoon-rice"],
            "notes": "",
        }
    ],
    "preparation": [
        {
            "order": 1,
            "dish": "herb-rice",
            "clean_before": ["board-a"],
            "note": "Use the declared sanitation procedure.",
        }
    ],
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="allergengrid",
        description=(
            "Turn explicit guest, ingredient, and resource declarations into an "
            "uncertainty-first allergen matrix."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"AllergenGrid {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a minimal case scaffold")
    init_parser.add_argument("directory", type=Path)
    init_parser.add_argument(
        "--profile",
        choices=("us", "eu", "global"),
        default="us",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate source structure and evidence declarations",
    )
    validate_parser.add_argument("case", type=Path)
    validate_parser.add_argument("--json", action="store_true")

    audit_parser = subparsers.add_parser(
        "audit",
        help="analyze every guest/dish combination",
    )
    audit_parser.add_argument("case", type=Path)
    audit_parser.add_argument("--json", action="store_true")
    audit_parser.add_argument("--strict", action="store_true")

    build_parser = subparsers.add_parser(
        "build",
        help="write HTML, CSV, JSON, labels, and a kitchen plan",
    )
    build_parser.add_argument("case", type=Path)
    build_parser.add_argument("--out", type=Path, required=True)
    build_parser.add_argument("--strict", action="store_true")

    pack_parser = subparsers.add_parser(
        "pack",
        help="create a deterministic, hash-verifiable ZIP",
    )
    pack_parser.add_argument("case", type=Path)
    pack_parser.add_argument("--out", type=Path, required=True)
    pack_parser.add_argument("--strict", action="store_true")

    verify_parser = subparsers.add_parser(
        "verify-pack",
        help="verify a package without extracting it",
    )
    verify_parser.add_argument("package", type=Path)
    verify_parser.add_argument("--json", action="store_true")

    explain_parser = subparsers.add_parser(
        "explain",
        help="show the reason path for one guest and dish",
    )
    explain_parser.add_argument("case", type=Path)
    explain_parser.add_argument("--guest", required=True)
    explain_parser.add_argument("--dish", required=True)
    explain_parser.add_argument("--json", action="store_true")
    return parser


def _finding_dict(finding: Finding) -> dict[str, str]:
    return {
        "code": finding.code,
        "severity": finding.severity.value,
        "path": finding.path,
        "message": finding.message,
        "hint": finding.hint,
    }


def _print_findings(findings: tuple[Finding, ...] | list[Finding]) -> None:
    if not findings:
        print("No findings.")
        return
    for finding in findings:
        print(
            f"{finding.severity.value.upper():7} {finding.code} {finding.path}: {finding.message}"
        )
        print(f"         repair: {finding.hint}")


def _result_exit(result: AnalysisResult, strict: bool) -> int:
    if result.has_errors:
        return EXIT_FINDINGS
    if strict and result.has_warnings:
        return EXIT_FINDINGS
    return EXIT_OK


def _init_case(directory: Path, profile: str) -> int:
    destination = directory.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise InputError(f"{destination}: refusing to write into a non-empty directory")
    destination.mkdir(parents=True, exist_ok=True)
    event = dict(_SCAFFOLD_EVENT)
    event["profile"] = profile
    (destination / EVENT_FILE).write_text(
        json.dumps(event, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (destination / GUESTS_FILE).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["guest_id", "name", "avoid_allergens", "required_diets", "notes"])
        writer.writerow(["guest-1", "Example guest", "", "", "Replace this row"])
    print(f"Created {destination}")
    print(f"Next: edit {EVENT_FILE} and {GUESTS_FILE}, then run allergengrid audit.")
    return EXIT_OK


def _validate(case_path: Path, json_output: bool) -> int:
    loaded = load_case(case_path)
    findings = validate_case(loaded)
    if json_output:
        print(
            json.dumps(
                {
                    "ok": not any(finding.severity is Severity.ERROR for finding in findings),
                    "input_digest": loaded.input_digest,
                    "findings": [_finding_dict(finding) for finding in findings],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            f"Validated {loaded.event.name!r}: {len(loaded.event.dishes)} dishes, "
            f"{len(loaded.guests)} guests."
        )
        _print_findings(findings)
    return (
        EXIT_FINDINGS
        if any(finding.severity is Severity.ERROR for finding in findings)
        else EXIT_OK
    )


def _audit(case_path: Path, json_output: bool, strict: bool) -> int:
    result = analyze_case(load_case(case_path))
    if json_output:
        print(json.dumps(analysis_data(result), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"AllergenGrid {__version__} — {result.loaded.event.name} "
            f"({result.loaded.event.revision})"
        )
        print(
            "matrix: "
            f"{result.status_counts.get(Status.CANDIDATE, 0)} candidate, "
            f"{result.status_counts.get(Status.HOLD, 0)} hold, "
            f"{result.status_counts.get(Status.BLOCK, 0)} block"
        )
        _print_findings(result.findings)
    return _result_exit(result, strict)


def _build(case_path: Path, output: Path, strict: bool) -> int:
    result = analyze_case(load_case(case_path))
    paths = build_outputs(result, output)
    print(f"Wrote {len(paths)} files to {output.expanduser().resolve()}")
    print(f"Open: {paths['report.html']}")
    return _result_exit(result, strict)


def _pack(case_path: Path, output: Path, strict: bool) -> int:
    result, package_path = create_package(case_path, output)
    verification = verify_package(package_path)
    if not verification.ok:
        for error in verification.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return EXIT_INPUT
    print(f"Created and verified {package_path} ({verification.checked_entries} hashed entries)")
    return _result_exit(result, strict)


def _verify(package_path: Path, json_output: bool) -> int:
    verification = verify_package(package_path)
    if json_output:
        print(
            json.dumps(
                {
                    "ok": verification.ok,
                    "checked_entries": verification.checked_entries,
                    "errors": list(verification.errors),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif verification.ok:
        print(f"PASS: verified {verification.checked_entries} hashed entries.")
    else:
        print("FAIL: package verification failed.")
        for error in verification.errors:
            print(f"  - {error}")
    return EXIT_OK if verification.ok else EXIT_FINDINGS


def _explain(
    case_path: Path,
    guest_id: str,
    dish_id: str,
    json_output: bool,
) -> int:
    result = analyze_case(load_case(case_path))
    try:
        assessment = result.assessment_for(guest_id, dish_id)
    except KeyError as exc:
        raise InputError(str(exc)) from exc
    payload = {
        "guest_id": assessment.guest_id,
        "dish_id": assessment.dish_id,
        "status": assessment.status.value,
        "reasons": [
            {
                "code": reason.code,
                "category": reason.category,
                "message": reason.message,
                "allergens": list(reason.allergens),
                "source_dish": reason.source_dish,
                "resource": reason.resource,
            }
            for reason in assessment.reasons
        ],
    }
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{assessment.guest_id} x {assessment.dish_id}: {assessment.status.value.upper()}")
        if assessment.reasons:
            for reason in assessment.reasons:
                print(f"  - {reason.code}: {reason.message}")
        else:
            print("  - No conflict found in the supplied declarations.")
            print("  - Re-check current labels, preparation, and guest needs before service.")
    return EXIT_OK


def run(argv: list[str] | None = None) -> int:
    """Run the CLI and return a stable exit code."""

    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "init":
            return _init_case(arguments.directory, arguments.profile)
        if arguments.command == "validate":
            return _validate(arguments.case, arguments.json)
        if arguments.command == "audit":
            return _audit(arguments.case, arguments.json, arguments.strict)
        if arguments.command == "build":
            return _build(arguments.case, arguments.out, arguments.strict)
        if arguments.command == "pack":
            return _pack(arguments.case, arguments.out, arguments.strict)
        if arguments.command == "verify-pack":
            return _verify(arguments.package, arguments.json)
        if arguments.command == "explain":
            return _explain(
                arguments.case,
                arguments.guest,
                arguments.dish,
                arguments.json,
            )
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return EXIT_INPUT
    raise AssertionError(f"unhandled command: {arguments.command}")


def main() -> NoReturn:
    """Console-script entry point."""

    raise SystemExit(run())
