"""Build reproducible AllergenGrid release artifacts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

from allergengrid import __version__

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "allergengrid"
EXAMPLE = ROOT / "examples" / "community-supper-safe"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
SOURCE_DATE_EPOCH = "1767225600"
PYZ_NAME = f"allergengrid-{__version__}.pyz"
EXAMPLE_NAME = f"allergengrid-example-{__version__}.zip"
WHEEL_NAME = f"allergengrid-{__version__}-py3-none-any.whl"
SDIST_NAME = f"allergengrid-{__version__}.tar.gz"
RELEASE_NAMES = {PYZ_NAME, EXAMPLE_NAME, WHEEL_NAME, SDIST_NAME}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def build_pyz(destination: Path) -> Path:
    output = destination / PYZ_NAME
    entrypoint = b"from allergengrid.cli import main\n\nif __name__ == '__main__':\n    main()\n"
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        archive.writestr(zip_info("__main__.py"), entrypoint)
        for source_path in sorted(SOURCE.rglob("*")):
            if not source_path.is_file() or source_path.suffix != ".py":
                continue
            relative = source_path.relative_to(SOURCE.parent).as_posix()
            archive.writestr(zip_info(relative), source_path.read_bytes())
    return output


def build_example(destination: Path) -> Path:
    output = destination / EXAMPLE_NAME
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source_path in sorted(EXAMPLE.rglob("*")):
            if source_path.is_file():
                relative = (
                    Path("community-supper-safe") / source_path.relative_to(EXAMPLE)
                ).as_posix()
                archive.writestr(zip_info(relative), source_path.read_bytes())
    return output


def build_python_packages(destination: Path) -> list[Path]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
        }
    )
    with tempfile.TemporaryDirectory(prefix="allergengrid-build-source-") as temporary:
        temporary_root = Path(temporary)
        source_root = temporary_root / "source"
        output_root = temporary_root / "output"
        shutil.copytree(
            ROOT,
            source_root,
            ignore=shutil.ignore_patterns(
                ".git",
                ".coverage",
                ".mypy_cache",
                ".ruff_cache",
                ".venv",
                "build",
                "dist",
                "*.egg-info",
                "__pycache__",
                "*.pyc",
            ),
        )
        output_root.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--wheel",
                "--sdist",
                "--outdir",
                str(output_root),
            ],
            cwd=source_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output_lines = result.stdout.splitlines()
        if result.returncode:
            details = "\n".join(output_lines[-80:])
            raise RuntimeError(f"Python package build failed:\n{details}")
        summary = next(
            (line for line in reversed(output_lines) if line.startswith("Successfully built ")),
            "Python package build completed",
        )
        print(summary)
        built_packages = sorted(
            path
            for path in output_root.iterdir()
            if path.suffix == ".whl" or path.name.endswith(".tar.gz")
        )
        sdist = output_root / SDIST_NAME
        if sdist not in built_packages:
            raise RuntimeError(f"build did not create {SDIST_NAME}")
        normalize_sdist(sdist)
        packages: list[Path] = []
        for built in built_packages:
            target = destination / built.name
            shutil.copyfile(built, target)
            packages.append(target)
        return packages


def normalize_sdist(path: Path) -> None:
    normalized_path = path.with_name(f".{path.name}.normalized")
    members: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, "r:gz") as source:
        for member in sorted(source.getmembers(), key=lambda item: item.name):
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(
                    f"unsupported sdist member type: {member.name} ({member.type!r})"
                )
            data: bytes | None = None
            if member.isfile():
                handle = source.extractfile(member)
                if handle is None:
                    raise RuntimeError(f"could not read sdist member: {member.name}")
                data = handle.read()
            member.mtime = int(SOURCE_DATE_EPOCH)
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.mode = 0o644 if member.isfile() else 0o755
            member.pax_headers = {}
            members.append((member, data))

    try:
        with (
            normalized_path.open("wb") as raw,
            gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw,
                mtime=int(SOURCE_DATE_EPOCH),
            ) as compressed,
            tarfile.open(
                mode="w",
                fileobj=compressed,
                format=tarfile.PAX_FORMAT,
            ) as destination,
        ):
            for member, data in members:
                destination.addfile(
                    member,
                    io.BytesIO(data) if data is not None else None,
                )
        normalized_path.replace(path)
    finally:
        normalized_path.unlink(missing_ok=True)


def require_members(name: str, actual: set[str], required: set[str]) -> None:
    missing = sorted(required - actual)
    unsafe = sorted(
        member
        for member in actual
        if member.startswith("/") or ".." in Path(member.replace("\\", "/")).parts
    )
    if missing or unsafe:
        raise RuntimeError(
            f"invalid {name}: missing={missing or 'none'}, unsafe={unsafe or 'none'}"
        )


def validate_zip(path: Path, required: set[str], *, fixed_time: bool = False) -> None:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(names) != len(set(names)):
            raise RuntimeError(f"duplicate archive member in {path.name}")
        require_members(path.name, set(names), required)
        if any(name.endswith((".pyc", ".pyo")) or "__pycache__/" in name for name in names):
            raise RuntimeError(f"bytecode cache leaked into {path.name}")
        if fixed_time and any(member.date_time != FIXED_TIME for member in members):
            raise RuntimeError(f"non-deterministic timestamp in {path.name}")


def validate_sdist(path: Path) -> None:
    prefix = f"allergengrid-{__version__}/"
    required = {
        f"{prefix}LICENSE",
        f"{prefix}README.md",
        f"{prefix}README.zh-CN.md",
        f"{prefix}docs/safety-model.md",
        f"{prefix}examples/community-supper-safe/event.json",
        f"{prefix}examples/community-supper-safe/guests.csv",
        f"{prefix}pyproject.toml",
        f"{prefix}scripts/verify.py",
        f"{prefix}src/allergengrid/cli.py",
        f"{prefix}tests/test_cli.py",
    }
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = {member.name.replace("\\", "/") for member in members}
        require_members(path.name, names, required)
        if any(member.mtime != int(SOURCE_DATE_EPOCH) for member in members):
            raise RuntimeError(f"non-deterministic timestamp in {path.name}")
        if any(
            member.uid != 0
            or member.gid != 0
            or member.uname
            or member.gname
            or (member.isfile() and member.mode != 0o644)
            or (member.isdir() and member.mode != 0o755)
            for member in members
        ):
            raise RuntimeError(f"non-normalized ownership or mode in {path.name}")


def validate_artifacts(artifacts: list[Path]) -> None:
    by_name = {path.name: path for path in artifacts}
    if set(by_name) != RELEASE_NAMES:
        raise RuntimeError(
            f"release artifact set mismatch: expected={sorted(RELEASE_NAMES)}, "
            f"received={sorted(by_name)}"
        )
    validate_zip(
        by_name[PYZ_NAME],
        {"__main__.py", "allergengrid/cli.py", "allergengrid/reports.py"},
        fixed_time=True,
    )
    validate_zip(
        by_name[EXAMPLE_NAME],
        {
            "community-supper-safe/event.json",
            "community-supper-safe/guests.csv",
        },
        fixed_time=True,
    )
    dist_info = f"allergengrid-{__version__}.dist-info"
    validate_zip(
        by_name[WHEEL_NAME],
        {
            "allergengrid/cli.py",
            "allergengrid/py.typed",
            f"{dist_info}/METADATA",
            f"{dist_info}/entry_points.txt",
            f"{dist_info}/licenses/LICENSE",
        },
    )
    validate_sdist(by_name[SDIST_NAME])


def build_once(destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = [build_pyz(destination), build_example(destination)]
    artifacts.extend(build_python_packages(destination))
    artifacts = sorted(artifacts)
    validate_artifacts(artifacts)
    return artifacts


def artifact_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: sha256(path)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    }


def verify_reproducible() -> None:
    with (
        tempfile.TemporaryDirectory(prefix="allergengrid-repro-a-") as first_raw,
        tempfile.TemporaryDirectory(prefix="allergengrid-repro-b-") as second_raw,
    ):
        first = Path(first_raw)
        second = Path(second_raw)
        build_once(first)
        time.sleep(2.1)
        build_once(second)
        first_hashes = artifact_hashes(first)
        second_hashes = artifact_hashes(second)
        if first_hashes != second_hashes:
            differing = sorted(set(first_hashes) | set(second_hashes))
            details = "\n".join(
                f"{name}: {first_hashes.get(name)} != {second_hashes.get(name)}"
                for name in differing
                if first_hashes.get(name) != second_hashes.get(name)
            )
            raise RuntimeError(f"release artifacts are not reproducible:\n{details}")
        print(f"PASS reproducible artifacts: {len(first_hashes)} files")


def clean_known_artifacts(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in destination.iterdir():
        if path.is_file() and (path.name == "SHA256SUMS" or path.name in RELEASE_NAMES):
            path.unlink()
    unexpected = sorted(path.name for path in destination.iterdir())
    if unexpected:
        raise RuntimeError(f"refusing to mix release with unexpected files: {unexpected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--check-reproducible", action="store_true")
    arguments = parser.parse_args()
    if arguments.check_reproducible:
        verify_reproducible()

    destination = arguments.out.resolve()
    clean_known_artifacts(destination)
    artifacts = build_once(destination)
    hashes = artifact_hashes(destination)
    checksum_path = destination / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())),
        encoding="utf-8",
    )
    print(f"Built {len(artifacts)} artifacts in {destination}")
    for artifact in artifacts:
        print(f"{sha256(artifact)}  {artifact.name}")
    print(f"{sha256(checksum_path)}  {checksum_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
