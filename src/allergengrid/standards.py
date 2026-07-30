"""Declared allergen profiles and conservative identifier matching.

AllergenGrid never infers allergens from an ingredient name.  This module only
normalizes explicit declarations and models the one intentional category
overlap between wheat and the EU "cereals containing gluten" category.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

ALLERGEN_LABELS: dict[str, str] = {
    "celery": "Celery",
    "crustaceans": "Crustacean shellfish",
    "egg": "Egg",
    "fish": "Fish",
    "gluten_cereals": "Cereals containing gluten",
    "lupin": "Lupin",
    "milk": "Milk",
    "molluscs": "Molluscs",
    "mustard": "Mustard",
    "peanut": "Peanut",
    "sesame": "Sesame",
    "soy": "Soybeans",
    "sulphites": "Sulphur dioxide and sulphites",
    "tree_nuts": "Tree nuts",
    "wheat": "Wheat",
}

ALLERGEN_PROFILES: dict[str, frozenset[str]] = {
    "us": frozenset(
        {
            "milk",
            "egg",
            "fish",
            "crustaceans",
            "tree_nuts",
            "wheat",
            "peanut",
            "soy",
            "sesame",
        }
    ),
    "eu": frozenset(
        {
            "gluten_cereals",
            "crustaceans",
            "egg",
            "fish",
            "peanut",
            "soy",
            "milk",
            "tree_nuts",
            "celery",
            "mustard",
            "sesame",
            "sulphites",
            "lupin",
            "molluscs",
        }
    ),
}
ALLERGEN_PROFILES["global"] = ALLERGEN_PROFILES["us"] | ALLERGEN_PROFILES["eu"]

PROFILE_LABELS = {
    "us": "United States major 9",
    "eu": "European Union regulated 14",
    "global": "Combined US and EU declaration set",
}

ALIASES: dict[str, str] = {
    "almond": "tree_nuts",
    "almonds": "tree_nuts",
    "brazil_nut": "tree_nuts",
    "brazil_nuts": "tree_nuts",
    "cashew": "tree_nuts",
    "cashews": "tree_nuts",
    "cereals_containing_gluten": "gluten_cereals",
    "crustacean_shellfish": "crustaceans",
    "eggs": "egg",
    "hazelnut": "tree_nuts",
    "hazelnuts": "tree_nuts",
    "macadamia": "tree_nuts",
    "macadamias": "tree_nuts",
    "nuts": "tree_nuts",
    "pecan": "tree_nuts",
    "pecans": "tree_nuts",
    "peanuts": "peanut",
    "pistachio": "tree_nuts",
    "pistachios": "tree_nuts",
    "sesame_seeds": "sesame",
    "shellfish": "crustaceans",
    "soybean": "soy",
    "soybeans": "soy",
    "sulfites": "sulphites",
    "tree_nut": "tree_nuts",
    "walnut": "tree_nuts",
    "walnuts": "tree_nuts",
}

REFERENCE_URLS = {
    "us": "https://www.fda.gov/consumers/consumer-updates/have-food-allergies-read-label",
    "eu": "https://food.ec.europa.eu/food-safety/campaign-2026/allergies_en",
    "cross_contact": (
        "https://www.cdc.gov/restaurant-food-safety/php/practices/food-allergy-reactions.html"
    ),
}

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def slugify(value: str) -> str:
    """Normalize a human-entered identifier without guessing its meaning."""

    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return ALIASES.get(normalized, normalized)


def validate_custom_id(value: str) -> bool:
    """Return whether a custom allergen identifier is stable and portable."""

    return bool(_ID_PATTERN.fullmatch(value))


def normalize_allergen(value: str, allowed: set[str] | frozenset[str]) -> str:
    """Normalize one explicit allergen identifier and require a declared profile entry."""

    normalized = slugify(value)
    if normalized not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(
            f"unknown allergen {value!r} (normalized to {normalized!r}); allowed: {allowed_text}"
        )
    return normalized


def overlap(left: str, right: str) -> bool:
    """Conservatively test whether two declared allergen categories overlap."""

    if left == right:
        return True
    return {left, right} == {"wheat", "gluten_cereals"}


def matching_hazards(hazards: Iterable[str], avoided: Iterable[str]) -> tuple[str, ...]:
    """Return declared hazards that overlap a guest's declared avoid list."""

    avoided_tuple = tuple(avoided)
    return tuple(
        sorted(
            hazard
            for hazard in set(hazards)
            if any(overlap(hazard, avoided_item) for avoided_item in avoided_tuple)
        )
    )


def label(allergen_id: str, custom_labels: dict[str, str] | None = None) -> str:
    """Return a display label for a standard or custom allergen."""

    if custom_labels and allergen_id in custom_labels:
        return custom_labels[allergen_id]
    return ALLERGEN_LABELS.get(allergen_id, allergen_id.replace("_", " ").title())
