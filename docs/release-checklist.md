# Release checklist

## Source and behavior

- [ ] `README.md` promises match implemented commands.
- [ ] Passing fixture returns `0` under `--strict`.
- [ ] Risky fixture returns `2` and exercises resource carry-over.
- [ ] No status or report calls `CANDIDATE` safe.
- [ ] Current official profile sources have been reviewed.

## Local gate

```bash
python scripts/verify.py --release
```

- [ ] Ruff, mypy, tests, and coverage pass.
- [ ] Secret/trailer scan passes.
- [ ] Reproducible builds pass after the deliberate delay.
- [ ] Wheel installs in a clean environment.
- [ ] `.pyz`, wheel, sdist, example ZIP, and `SHA256SUMS` exist.

## Git identity and history

```bash
git status --short
git log --format=fuller
git shortlog -sne HEAD
git log --all --format=%B | rg -i "Co-authored-by"
```

- [ ] Worktree is clean.
- [ ] Author and committer are the intended identity.
- [ ] Only intended contributors appear.
- [ ] No `Co-authored-by` trailers exist.

## Remote and CI

- [ ] Public repository metadata and topics are correct.
- [ ] Exact commit is on `main`.
- [ ] CI passes on Linux and Windows for Python 3.11–3.13.
- [ ] Release-gate artifact can be downloaded.
- [ ] Tag `vX.Y.Z` points to the tested commit.
- [ ] Release workflow succeeds.

## Public release verification

- [ ] Release is public and not a draft.
- [ ] All expected assets are present.
- [ ] Downloaded `SHA256SUMS` matches every downloaded asset.
- [ ] Downloaded `.pyz --version` works.
- [ ] Downloaded example and `.pyz` pass strict audit.
- [ ] GitHub contributors list contains only intended contributors.
- [ ] README badges and links resolve anonymously.

## Notification

Only after every required item above:

- [ ] Send the repository URL, release URL, tag/commit, checks, install command,
      acceptance command, and known limitations.
