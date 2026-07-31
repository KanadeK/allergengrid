"""Strict, dependency-free case loading."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, NoReturn

from allergengrid.models import (
    Dish,
    Event,
    Guest,
    Ingredient,
    LoadedCase,
    PreparationStep,
    Resource,
)
from allergengrid.standards import (
    ALLERGEN_PROFILES,
    normalize_allergen,
    slugify,
    validate_custom_id,
)

EVENT_FILE = "event.json"
GUESTS_FILE = "guests.csv"

RESOURCE_KINDS = frozenset({"surface", "utensil", "appliance", "oil", "service", "other"})
_ENTITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class InputError(ValueError):
    """Raised when source data cannot be interpreted without guessing."""


def _fail(path: str, message: str) -> NoReturn:
    raise InputError(f"{path}: {message}")


def _require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "expected an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "expected an array")
    return value


def _require_str(
    value: Any,
    path: str,
    *,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        _fail(path, "expected a string")
    cleaned = value.strip()
    if not allow_empty and not cleaned:
        _fail(path, "must not be empty")
    return cleaned


def _optional_str(value: Any, path: str) -> str:
    if value is None:
        return ""
    return _require_str(value, path, allow_empty=True)


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "expected true or false")
    return value


def _require_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "expected an integer")
    return int(value)


def _unique(values: Iterable[str], path: str) -> tuple[str, ...]:
    collected = tuple(values)
    if len(collected) != len(set(collected)):
        _fail(path, "must not contain duplicate values")
    return collected


def _string_list(value: Any, path: str) -> tuple[str, ...]:
    items = _require_list(value, path)
    return _unique(
        (_require_str(item, f"{path}[{index}]") for index, item in enumerate(items)),
        path,
    )


def _identifier(value: Any, path: str) -> str:
    raw = _require_str(value, path)
    normalized = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-_")
    if not _ENTITY_ID_PATTERN.fullmatch(normalized):
        _fail(path, f"{raw!r} is not a portable identifier")
    return normalized


def _load_custom_allergens(
    raw_items: Any,
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for index, raw_item in enumerate(_require_list(raw_items, "event.custom_allergens")):
        item = _require_dict(raw_item, f"event.custom_allergens[{index}]")
        raw_id = _require_str(item.get("id"), f"event.custom_allergens[{index}].id")
        allergen_id = slugify(raw_id)
        if not validate_custom_id(allergen_id):
            _fail(
                f"event.custom_allergens[{index}].id",
                f"{raw_id!r} is not a portable allergen identifier",
            )
        label = _require_str(item.get("label"), f"event.custom_allergens[{index}].label")
        if allergen_id in labels:
            _fail(f"event.custom_allergens[{index}].id", "duplicate custom allergen")
        if allergen_id in ALLERGEN_PROFILES["global"]:
            _fail(
                f"event.custom_allergens[{index}].id",
                "standard allergen IDs cannot be redeclared",
            )
        labels[allergen_id] = label
    return labels


def _allergen_set(value: Any, path: str, allowed: set[str]) -> frozenset[str]:
    raw_items = _string_list(value, path)
    normalized: list[str] = []
    for index, item in enumerate(raw_items):
        try:
            normalized.append(normalize_allergen(item, allowed))
        except ValueError as exc:
            _fail(f"{path}[{index}]", str(exc))
    if len(normalized) != len(set(normalized)):
        _fail(path, "contains duplicate values after alias normalization")
    return frozenset(normalized)


def _diet_set(value: Any, path: str) -> frozenset[str]:
    values = _string_list(value, path)
    normalized = tuple(slugify(item).replace("_", "-") for item in values)
    if len(normalized) != len(set(normalized)):
        _fail(path, "contains duplicate values after normalization")
    return frozenset(normalized)


def _load_ingredient(
    raw_value: Any,
    path: str,
    allowed: set[str],
) -> Ingredient:
    item = _require_dict(raw_value, path)
    return Ingredient(
        name=_require_str(item.get("name"), f"{path}.name"),
        contains=_allergen_set(item.get("contains", []), f"{path}.contains", allowed),
        may_contain=_allergen_set(
            item.get("may_contain", []),
            f"{path}.may_contain",
            allowed,
        ),
        verified=_require_bool(item.get("verified", False), f"{path}.verified"),
        evidence=_optional_str(item.get("evidence", ""), f"{path}.evidence"),
    )


def _load_dish(raw_value: Any, index: int, allowed: set[str]) -> Dish:
    path = f"event.dishes[{index}]"
    item = _require_dict(raw_value, path)
    ingredients = tuple(
        _load_ingredient(raw_ingredient, f"{path}.ingredients[{ingredient_index}]", allowed)
        for ingredient_index, raw_ingredient in enumerate(
            _require_list(item.get("ingredients"), f"{path}.ingredients")
        )
    )
    if not ingredients:
        _fail(f"{path}.ingredients", "must contain at least one ingredient declaration")
    return Dish(
        dish_id=_identifier(item.get("id"), f"{path}.id"),
        name=_require_str(item.get("name"), f"{path}.name"),
        ingredients=ingredients,
        diet_tags=_diet_set(item.get("diet_tags", []), f"{path}.diet_tags"),
        free_from=_allergen_set(item.get("free_from", []), f"{path}.free_from", allowed),
        prep_resources=tuple(
            _identifier(resource, f"{path}.prep_resources[{resource_index}]")
            for resource_index, resource in enumerate(
                _string_list(item.get("prep_resources", []), f"{path}.prep_resources")
            )
        ),
        service_resources=tuple(
            _identifier(resource, f"{path}.service_resources[{resource_index}]")
            for resource_index, resource in enumerate(
                _string_list(item.get("service_resources", []), f"{path}.service_resources")
            )
        ),
        notes=_optional_str(item.get("notes", ""), f"{path}.notes"),
    )


def _load_resource(raw_value: Any, index: int) -> Resource:
    path = f"event.resources[{index}]"
    item = _require_dict(raw_value, path)
    kind = _identifier(item.get("kind", "other"), f"{path}.kind")
    if kind not in RESOURCE_KINDS:
        _fail(f"{path}.kind", f"must be one of: {', '.join(sorted(RESOURCE_KINDS))}")
    dedicated_raw = item.get("dedicated_to")
    dedicated_to = (
        None if dedicated_raw in (None, "") else _identifier(dedicated_raw, f"{path}.dedicated_to")
    )
    return Resource(
        resource_id=_identifier(item.get("id"), f"{path}.id"),
        name=_require_str(item.get("name"), f"{path}.name"),
        kind=kind,
        cleanable=_require_bool(item.get("cleanable", True), f"{path}.cleanable"),
        dedicated_to=dedicated_to,
    )


def _load_step(raw_value: Any, index: int) -> PreparationStep:
    path = f"event.preparation[{index}]"
    item = _require_dict(raw_value, path)
    return PreparationStep(
        order=_require_int(item.get("order"), f"{path}.order"),
        dish_id=_identifier(item.get("dish"), f"{path}.dish"),
        clean_before=tuple(
            _identifier(resource, f"{path}.clean_before[{resource_index}]")
            for resource_index, resource in enumerate(
                _string_list(item.get("clean_before", []), f"{path}.clean_before")
            )
        ),
        note=_optional_str(item.get("note", ""), f"{path}.note"),
    )


def _load_event(raw: Any) -> Event:
    root = _require_dict(raw, "event")
    schema_version = _require_int(root.get("schema_version"), "event.schema_version")
    if schema_version != 1:
        _fail("event.schema_version", "only schema version 1 is supported")
    profile = _identifier(root.get("profile"), "event.profile")
    if profile not in ALLERGEN_PROFILES:
        _fail("event.profile", "must be one of: us, eu, global")
    custom_labels = _load_custom_allergens(root.get("custom_allergens", []))
    allowed = set(ALLERGEN_PROFILES[profile]) | set(custom_labels)
    dishes = tuple(
        _load_dish(raw_dish, index, allowed)
        for index, raw_dish in enumerate(_require_list(root.get("dishes"), "event.dishes"))
    )
    if not dishes:
        _fail("event.dishes", "must contain at least one dish")
    resources = tuple(
        _load_resource(raw_resource, index)
        for index, raw_resource in enumerate(
            _require_list(root.get("resources", []), "event.resources")
        )
    )
    preparation = tuple(
        _load_step(raw_step, index)
        for index, raw_step in enumerate(
            _require_list(root.get("preparation", []), "event.preparation")
        )
    )
    return Event(
        schema_version=schema_version,
        name=_require_str(root.get("name"), "event.name"),
        event_date=_require_str(root.get("date"), "event.date"),
        revision=_require_str(root.get("revision"), "event.revision"),
        profile=profile,
        custom_allergen_labels=custom_labels,
        dishes=dishes,
        resources=resources,
        preparation=preparation,
    )


def _split_cell(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split("|") if part.strip())


def _load_guests(path: Path, allowed: set[str]) -> tuple[Guest, ...]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {
                "guest_id",
                "name",
                "avoid_allergens",
                "required_diets",
                "notes",
            }
            if reader.fieldnames is None:
                _fail(GUESTS_FILE, "missing header row")
            missing = required - set(reader.fieldnames)
            if missing:
                _fail(GUESTS_FILE, f"missing columns: {', '.join(sorted(missing))}")
            guests: list[Guest] = []
            for row_index, row in enumerate(reader, start=2):
                avoid_raw = _split_cell(row.get("avoid_allergens", ""))
                diets_raw = _split_cell(row.get("required_diets", ""))
                guests.append(
                    Guest(
                        guest_id=_identifier(
                            row.get("guest_id"),
                            f"{GUESTS_FILE}:{row_index}.guest_id",
                        ),
                        name=_require_str(
                            row.get("name"),
                            f"{GUESTS_FILE}:{row_index}.name",
                        ),
                        avoid_allergens=_allergen_set(
                            list(avoid_raw),
                            f"{GUESTS_FILE}:{row_index}.avoid_allergens",
                            allowed,
                        ),
                        required_diets=_diet_set(
                            list(diets_raw),
                            f"{GUESTS_FILE}:{row_index}.required_diets",
                        ),
                        notes=_optional_str(
                            row.get("notes", ""),
                            f"{GUESTS_FILE}:{row_index}.notes",
                        ),
                    )
                )
    except UnicodeDecodeError as exc:
        raise InputError(f"{GUESTS_FILE}: expected UTF-8 text") from exc
    if not guests:
        _fail(GUESTS_FILE, "must contain at least one guest")
    return tuple(guests)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_case(source_dir: str | Path) -> LoadedCase:
    """Load one case directory and hash its exact source bytes."""

    root = Path(source_dir).expanduser().resolve()
    if not root.is_dir():
        raise InputError(f"{root}: case directory does not exist")
    event_path = root / EVENT_FILE
    guests_path = root / GUESTS_FILE
    for required_path in (event_path, guests_path):
        if not required_path.is_file():
            raise InputError(f"{required_path}: required file is missing")

    event_bytes = event_path.read_bytes()
    guests_bytes = guests_path.read_bytes()
    try:
        event_raw = json.loads(event_bytes.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise InputError(f"{event_path}: expected UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"{event_path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}") from exc

    event = _load_event(event_raw)
    allowed = set(ALLERGEN_PROFILES[event.profile]) | set(event.custom_allergen_labels)
    guests = _load_guests(guests_path, allowed)
    hashes = {
        EVENT_FILE: _sha256(event_bytes),
        GUESTS_FILE: _sha256(guests_bytes),
    }
    digest_payload = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    return LoadedCase(
        source_dir=root,
        event=event,
        guests=guests,
        input_hashes=hashes,
        input_digest=_sha256(digest_payload.encode("utf-8")),
    )
