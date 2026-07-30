# Troubleshooting and repair guide

## Read the exit code first

| Exit | Meaning | First action |
| ---: | --- | --- |
| `0` | Selected gate passed | Review outputs with the organizer/guest |
| `1` | Input/files/archive cannot be read safely | Fix syntax, encoding, path, or ZIP structure |
| `2` | Findings failed the gate or integrity failed | Read the first finding/hash mismatch and repair source |

Use this sequence:

```bash
allergengrid validate my-event
allergengrid audit my-event
allergengrid audit my-event --json > analysis.json
```

Do not hide warnings to obtain a green command. Resolve them or run without
`--strict` only when your documented policy permits warnings.

## Input failures (`1`)

### Invalid JSON

Message:

```text
INPUT ERROR: ...event.json:LINE:COLUMN: invalid JSON
```

Repair:

1. open the stated line/column;
2. remove trailing commas and comments;
3. ensure keys and strings use double quotes;
4. save as UTF-8;
5. rerun `validate`.

### Missing CSV columns

Use the exact header:

```csv
guest_id,name,avoid_allergens,required_diets,notes
```

Preserve empty cells rather than deleting columns.

### Unknown allergen

Use an ID from the event profile or declare a custom explicit allergen. Do not
silence the error by mapping an ingredient to a guessed category.

### Non-empty `init` destination

`init` refuses to write into a non-empty directory. Choose a new directory or
create the two files manually. The command never merges with existing files.

## Finding codes (`2` under the applicable gate)

| Code | Meaning | Repair |
| --- | --- | --- |
| `AG001` | Event date is not ISO | Use `YYYY-MM-DD` |
| `AG002` | Duplicate dish/resource/guest ID | Assign stable unique IDs and update references |
| `AG003` | Duplicate preparation order | Use one positive order per step |
| `AG004` | Preparation order is zero/negative | Number from 1 upward |
| `AG005` | Preparation step references unknown dish | Correct the dish ID or restore the dish |
| `AG006` | Cleaning references unknown resource | Declare/correct the resource |
| `AG007` | Cleaned resource is not used by target dish | Correct the ID or add it to `prep_resources` |
| `AG008` | Cleaning declared for non-cleanable resource | Replace or dedicate the resource |
| `AG009` | Dish has multiple preparation steps | Keep one step and list all resources on the dish |
| `AG010` | Dish uses resources but has no preparation order | Add one preparation step |
| `AG011` | Dish references unknown resource | Declare or correct it |
| `AG012` | Same allergen is both `contains` and `may_contain` | Put it in the correct single category |
| `AG013` | `verified: true` has no evidence | Record label/recipe/source and check date |
| `AG014` | Ingredient is unverified | Check current source; update declaration and evidence |
| `AG015` | `free_from` directly contradicts `contains` | Remove claim or correct/re-verify ingredients |
| `AG016` | `free_from` conflicts with `may_contain` | Hold claim until uncertainty is resolved |
| `AG017` | Resource is dedicated to unknown dish | Correct `dedicated_to` |
| `AG018` | Dedicated resource used by another dish | Use a different resource or remove the false dedication |
| `AG201` | Preparation resource carries prior exposure | Add verified cleaning, replacement, or dedication |
| `AG202` | Dish has shared-service carry-over | Assign a unique utensil/container |
| `AG203` | Resource path invalidates `free_from` claim | Remove the claim until the path is resolved |
| `AG204` | Service resource is shared across dishes | Use dedicated service resources |
| `AG301` | Constrained guest has no candidate dish | Add/verify an option or contact the guest before event |

Use `explain` for a specific matrix cell:

```bash
allergengrid explain my-event --guest guest-1 --dish dish-1
```

## Package verification failures

### SHA-256 or size mismatch

The package changed after its manifest was created.

1. Do not use the package as an intact archive.
2. Recover the original source case.
3. Run `audit --strict`.
4. Build and pack again.
5. Verify the new pack before sharing.

Do not edit files inside a finished ZIP.

### Duplicate, unlisted, missing, or unsafe entry

Treat the ZIP as malformed or tampered. AllergenGrid deliberately refuses to
extract it. Obtain a fresh pack from the source case.

### Package too large

The v0.1 pack contains declarations and reports, not original photos or
attachments. Remove unrelated files and recreate it with `allergengrid pack`.

## Installation failures

### `python` not found

Install Python 3.11+ and verify:

```bash
python --version
```

On Windows, the launcher may be:

```powershell
py -3.12 --version
```

### `allergengrid` not found

Activate the same virtual environment used for installation, or run:

```bash
python -m allergengrid --version
```

### Development tools missing

```bash
python -m pip install -e ".[dev]"
python scripts/verify.py
```

The runtime itself has no third-party dependencies.

## Release gate failure

Run the failing command printed after `+` by `scripts/verify.py`.

- Ruff: apply formatting with `python -m ruff format .`, then review the diff.
- mypy: fix the type boundary; do not add broad ignores.
- coverage: add a meaningful passing or failure-path test; do not lower the
  threshold to ship.
- reproducibility: inspect both artifact hashes and time-dependent metadata.
- clean install: inspect the wheel contents and console entry point.
- secret scan: remove the material from all commits before publication.

If setuptools reports that license classifiers were superseded by license
expressions, keep the SPDX `license = "MIT"` declaration and remove the old
`License :: OSI Approved :: MIT License` classifier. Do not remove or change
the actual `LICENSE` file.

If the sdist timestamp check fails, do not delete the check. Confirm that
`normalize_sdist()` fixes the gzip header and every tar member's timestamp,
owner, mode, and order before the two builds are compared.

If a Windows build backend stops while copying into `build/bdist...`, confirm
that `build_python_packages()` still uses a fresh temporary source and output
tree for every build. Do not make reproducibility depend on stale repository
build state.

After repair, rerun:

```bash
python scripts/verify.py --release
```
