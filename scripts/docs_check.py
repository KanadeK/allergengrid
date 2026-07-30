"""Validate local Markdown links without requiring a network connection."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
ROOT_DOCUMENTS = (
    "README.md",
    "README.zh-CN.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)


def markdown_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_DOCUMENTS]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    return files


def local_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip("<>")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("#"):
        return None
    path_text = unquote(parsed.path)
    if not path_text:
        return None
    candidate = (source.parent / path_text).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError(
            f"{source.relative_to(ROOT)}: link escapes repository: {target}"
        ) from error
    return candidate


def main() -> int:
    failures: list[str] = []
    files = markdown_files()
    for source in files:
        if not source.is_file():
            failures.append(f"missing required document: {source.relative_to(ROOT)}")
            continue
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            for match in LINK.finditer(line):
                raw_target = match.group(1)
                try:
                    target = local_target(source, raw_target)
                except ValueError as error:
                    failures.append(str(error))
                    continue
                if target is not None and not target.exists():
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: "
                        f"missing local link target {raw_target}"
                    )
    if failures:
        print("FAIL documentation links")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"PASS documentation links: {len(files)} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
