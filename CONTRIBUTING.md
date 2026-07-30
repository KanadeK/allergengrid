# Contributing

Thank you for improving AllergenGrid.

## Safety first

Changes that affect classification or reports must preserve these rules:

- never call `CANDIDATE` safe;
- never infer allergens from ingredient names and present the inference as fact;
- unknown data must not silently become a candidate;
- a new rule needs a passing and failing deterministic test;
- cite the source or explain the conservative rationale;
- do not include real guest or medical data in code, fixtures, issues, or logs.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/verify.py
```

## Pull requests

Keep each pull request focused. Describe:

- the user problem;
- the exact behavior change;
- safety and privacy impact;
- tests added;
- commands run;
- compatibility or schema impact.

Run `python scripts/verify.py --release` for packaging or release changes.

Do not add generated `build/`, `dist/`, caches, or real event data.

## Design guidance

- Core runtime dependencies should remain zero unless a concrete feature cannot
  be implemented safely otherwise.
- Loaders reject ambiguity; importers should convert to the existing explicit
  case format.
- New reports consume `AnalysisResult`; do not fork classification logic.
- Keep outputs deterministic and self-contained.
- Schema changes require a version and migration/compatibility plan.

## Issues

Use synthetic minimal data. If a problem only reproduces with sensitive data,
replace names and values consistently before sharing. Security vulnerabilities
belong in a private GitHub security advisory, not a public issue.
