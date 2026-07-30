"""Require a release tag to match the package version exactly."""

from __future__ import annotations

import argparse
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def expected_tag() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if not isinstance(version, str):
        raise TypeError("project.version must be a string")
    return f"v{version}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", nargs="?", default=os.environ.get("GITHUB_REF_NAME"))
    arguments = parser.parse_args()
    expected = expected_tag()
    if arguments.tag != expected:
        print(f"FAIL release tag: expected {expected!r}, received {arguments.tag!r}")
        return 1
    print(f"PASS release tag: {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
