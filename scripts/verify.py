"""One-command local and release acceptance gate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, environment: dict[str, str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def clean_install_check(environment: dict[str, str]) -> None:
    wheels = sorted((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel, found {len(wheels)}")
    with tempfile.TemporaryDirectory(prefix="allergengrid-install-") as temporary:
        virtual = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(virtual)
        python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        clean_environment = environment.copy()
        clean_environment.pop("PYTHONPATH", None)
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                str(wheels[0]),
            ],
            environment=clean_environment,
        )
        run(
            [str(python), "-m", "allergengrid", "--version"],
            environment=clean_environment,
        )
        run(
            [
                str(python),
                "-m",
                "allergengrid",
                "audit",
                str(ROOT / "examples" / "community-supper-safe"),
                "--strict",
            ],
            environment=clean_environment,
        )


def single_file_check(environment: dict[str, str]) -> None:
    archives = sorted((ROOT / "dist").glob("*.pyz"))
    if len(archives) != 1:
        raise RuntimeError(f"expected exactly one pyz, found {len(archives)}")
    run([sys.executable, str(archives[0]), "--version"], environment=environment)
    run(
        [
            sys.executable,
            str(archives[0]),
            "audit",
            str(ROOT / "examples" / "community-supper-safe"),
            "--strict",
        ],
        environment=environment,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true")
    arguments = parser.parse_args()

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONHASHSEED"] = "0"
    python = sys.executable

    run([python, "-m", "ruff", "check", "."], environment=environment)
    run([python, "-m", "ruff", "format", "--check", "."], environment=environment)
    run([python, "-m", "mypy", "src", "scripts"], environment=environment)
    run([python, "-m", "coverage", "erase"], environment=environment)
    run(
        [
            python,
            "-m",
            "coverage",
            "run",
            "--branch",
            "--source=allergengrid",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ],
        environment=environment,
    )
    run(
        [python, "-m", "coverage", "report", "--fail-under=90"],
        environment=environment,
    )
    run([python, "scripts/demo.py"], environment=environment)
    run([python, "scripts/docs_check.py"], environment=environment)
    run([python, "scripts/secret_scan.py"], environment=environment)

    if arguments.release:
        run(
            [
                python,
                "scripts/package_release.py",
                "--check-reproducible",
            ],
            environment=environment,
        )
        single_file_check(environment)
        clean_install_check(environment)
    print("PASS AllergenGrid verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
