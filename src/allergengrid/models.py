"""Typed domain models used by loaders, analyzers, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Severity(StrEnum):
    """Finding severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Status(StrEnum):
    """Action-oriented guest/dish classification."""

    BLOCK = "block"
    HOLD = "hold"
    CANDIDATE = "candidate"


@dataclass(frozen=True, slots=True)
class Ingredient:
    """One ingredient declaration supplied by an organizer."""

    name: str
    contains: frozenset[str]
    may_contain: frozenset[str]
    verified: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class Dish:
    """A dish plus its declared preparation and service resources."""

    dish_id: str
    name: str
    ingredients: tuple[Ingredient, ...]
    diet_tags: frozenset[str]
    free_from: frozenset[str]
    prep_resources: tuple[str, ...]
    service_resources: tuple[str, ...]
    notes: str = ""

    @property
    def contains(self) -> frozenset[str]:
        return frozenset(
            allergen for ingredient in self.ingredients for allergen in ingredient.contains
        )

    @property
    def may_contain(self) -> frozenset[str]:
        return frozenset(
            allergen for ingredient in self.ingredients for allergen in ingredient.may_contain
        )

    @property
    def has_unverified_ingredients(self) -> bool:
        return any(not ingredient.verified for ingredient in self.ingredients)

    @property
    def unverified_ingredients(self) -> tuple[str, ...]:
        return tuple(ingredient.name for ingredient in self.ingredients if not ingredient.verified)


@dataclass(frozen=True, slots=True)
class Resource:
    """A preparation surface, utensil, appliance, oil, or service item."""

    resource_id: str
    name: str
    kind: str
    cleanable: bool
    dedicated_to: str | None


@dataclass(frozen=True, slots=True)
class PreparationStep:
    """Declared preparation order and cleaning boundary."""

    order: int
    dish_id: str
    clean_before: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True, slots=True)
class Guest:
    """One guest's explicit constraints."""

    guest_id: str
    name: str
    avoid_allergens: frozenset[str]
    required_diets: frozenset[str]
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Event:
    """Loaded event definition."""

    schema_version: int
    name: str
    event_date: str
    revision: str
    profile: str
    custom_allergen_labels: dict[str, str]
    dishes: tuple[Dish, ...]
    resources: tuple[Resource, ...]
    preparation: tuple[PreparationStep, ...]

    @property
    def dish_by_id(self) -> dict[str, Dish]:
        return {dish.dish_id: dish for dish in self.dishes}

    @property
    def resource_by_id(self) -> dict[str, Resource]:
        return {resource.resource_id: resource for resource in self.resources}


@dataclass(frozen=True, slots=True)
class LoadedCase:
    """An event, its guests, and byte-level input evidence."""

    source_dir: Path
    event: Event
    guests: tuple[Guest, ...]
    input_hashes: dict[str, str]
    input_digest: str


@dataclass(frozen=True, slots=True)
class Reason:
    """A traceable reason behind a status or finding."""

    code: str
    category: str
    message: str
    allergens: tuple[str, ...] = ()
    source_dish: str | None = None
    resource: str | None = None


@dataclass(frozen=True, slots=True)
class Finding:
    """A validation or risk finding with an actionable repair hint."""

    code: str
    severity: Severity
    message: str
    path: str
    hint: str


@dataclass(frozen=True, slots=True)
class Assessment:
    """One guest/dish result."""

    guest_id: str
    dish_id: str
    status: Status
    reasons: tuple[Reason, ...]


@dataclass(frozen=True, slots=True)
class RecommendedStep:
    """A conservative, review-required preparation-order suggestion."""

    order: int
    dish_id: str
    clean_before: tuple[str, ...]
    replace_resources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CrossContactResult:
    """Cross-contact traces created from declared resource reuse."""

    reasons_by_dish: dict[str, tuple[Reason, ...]]
    shared_service_resources: dict[str, tuple[str, ...]]
    recommended_steps: tuple[RecommendedStep, ...]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Complete deterministic analysis for one case."""

    loaded: LoadedCase
    findings: tuple[Finding, ...]
    assessments: tuple[Assessment, ...]
    cross_contact: CrossContactResult
    status_counts: dict[Status, int] = field(default_factory=dict)

    def assessment_for(self, guest_id: str, dish_id: str) -> Assessment:
        for assessment in self.assessments:
            if assessment.guest_id == guest_id and assessment.dish_id == dish_id:
                return assessment
        raise KeyError(f"assessment not found for guest={guest_id!r}, dish={dish_id!r}")

    @property
    def has_errors(self) -> bool:
        return any(finding.severity is Severity.ERROR for finding in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(finding.severity is Severity.WARNING for finding in self.findings)
