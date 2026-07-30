"""Deterministic share packages and offline integrity verification."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from allergengrid import __version__
from allergengrid.analysis import analyze_case
from allergengrid.loader import EVENT_FILE, GUESTS_FILE, load_case
from allergengrid.models import AnalysisResult
from allergengrid.reports import build_outputs

MAX_ENTRIES = 1_000
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class PackageVerification:
    """Result of verifying a portable AllergenGrid package."""

    ok: bool
    errors: tuple[str, ...]
    checked_entries: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def _safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def create_package(
    case_dir: str | Path,
    output_path: str | Path,
) -> tuple[AnalysisResult, Path]:
    """Create a byte-reproducible ZIP containing inputs, reports, and a hash manifest."""

    loaded = load_case(case_dir)
    result = analyze_case(loaded)
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="allergengrid-pack-") as temporary:
        report_dir = Path(temporary) / "report"
        report_paths = build_outputs(result, report_dir)
        entries: dict[str, bytes] = {
            f"inputs/{EVENT_FILE}": (loaded.source_dir / EVENT_FILE).read_bytes(),
            f"inputs/{GUESTS_FILE}": (loaded.source_dir / GUESTS_FILE).read_bytes(),
        }
        entries.update(
            {f"report/{name}": path.read_bytes() for name, path in sorted(report_paths.items())}
        )
        package_manifest: dict[str, object] = {
            "schema_version": 1,
            "tool": {"name": "AllergenGrid", "version": __version__},
            "input_digest": loaded.input_digest,
            "entries": {
                name: {"sha256": _sha256(data), "size": len(data)}
                for name, data in sorted(entries.items())
            },
        }
        manifest_bytes = (
            json.dumps(
                package_manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        with tempfile.NamedTemporaryFile(
            prefix="allergengrid-",
            suffix=".zip",
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        try:
            with zipfile.ZipFile(
                temporary_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for name, data in sorted(entries.items()):
                    archive.writestr(_zip_info(name), data)
                archive.writestr(_zip_info("package-manifest.json"), manifest_bytes)
            temporary_path.replace(destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    return result, destination


def verify_package(package_path: str | Path) -> PackageVerification:
    """Verify names, sizes, and SHA-256 hashes without extracting the archive."""

    path = Path(package_path).expanduser().resolve()
    errors: list[str] = []
    checked = 0
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > MAX_ENTRIES:
                errors.append(f"too many entries: {len(infos)} > {MAX_ENTRIES}")
            if len(names) != len(set(names)):
                errors.append("archive contains duplicate entry names")
            unsafe = sorted(name for name in names if not _safe_member_name(name))
            if unsafe:
                errors.append(f"unsafe entry names: {', '.join(unsafe)}")
            total_size = sum(info.file_size for info in infos)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                errors.append(
                    f"uncompressed package is too large: {total_size} > {MAX_UNCOMPRESSED_BYTES}"
                )
            if "package-manifest.json" not in names:
                errors.append("package-manifest.json is missing")
                return PackageVerification(False, tuple(errors), checked)
            try:
                manifest_raw = json.loads(archive.read("package-manifest.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
                errors.append(f"invalid package manifest: {exc}")
                return PackageVerification(False, tuple(errors), checked)
            if not isinstance(manifest_raw, dict):
                errors.append("package manifest must be an object")
                return PackageVerification(False, tuple(errors), checked)
            entries_raw = manifest_raw.get("entries")
            if not isinstance(entries_raw, dict):
                errors.append("package manifest entries must be an object")
                return PackageVerification(False, tuple(errors), checked)
            expected_names = set(entries_raw)
            actual_names = set(names) - {"package-manifest.json"}
            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)
            if missing:
                errors.append(f"missing entries: {', '.join(missing)}")
            if extra:
                errors.append(f"unlisted entries: {', '.join(extra)}")
            for name in sorted(expected_names & actual_names):
                metadata = entries_raw[name]
                if not isinstance(metadata, dict):
                    errors.append(f"{name}: manifest metadata must be an object")
                    continue
                expected_hash = metadata.get("sha256")
                expected_size = metadata.get("size")
                data = archive.read(name)
                checked += 1
                if not isinstance(expected_size, int) or expected_size != len(data):
                    errors.append(
                        f"{name}: size mismatch (expected {expected_size!r}, got {len(data)})"
                    )
                actual_hash = _sha256(data)
                if not isinstance(expected_hash, str) or expected_hash != actual_hash:
                    errors.append(
                        f"{name}: SHA-256 mismatch (expected {expected_hash!r}, got {actual_hash})"
                    )
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"cannot read package: {exc}")
    return PackageVerification(not errors, tuple(errors), checked)
