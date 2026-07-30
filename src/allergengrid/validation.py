"""Semantic validation for loaded AllergenGrid cases."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from allergengrid.models import Finding, LoadedCase, Severity
from allergengrid.standards import matching_hazards


def _finding(
    code: str,
    severity: Severity,
    message: str,
    path: str,
    hint: str,
) -> Finding:
    return Finding(code=code, severity=severity, message=message, path=path, hint=hint)


def validate_case(loaded: LoadedCase) -> tuple[Finding, ...]:
    """Return deterministic structural and source-quality findings."""

    event = loaded.event
    findings: list[Finding] = []

    try:
        date.fromisoformat(event.event_date)
    except ValueError:
        findings.append(
            _finding(
                "AG001",
                Severity.ERROR,
                f"event date {event.event_date!r} is not ISO YYYY-MM-DD",
                "event.date",
                "Use an explicit calendar date such as 2026-08-15.",
            )
        )

    for kind, identifiers in (
        ("dish", [dish.dish_id for dish in event.dishes]),
        ("resource", [resource.resource_id for resource in event.resources]),
        ("guest", [guest.guest_id for guest in loaded.guests]),
    ):
        for identifier, count in sorted(Counter(identifiers).items()):
            if count > 1:
                findings.append(
                    _finding(
                        "AG002",
                        Severity.ERROR,
                        f"duplicate {kind} identifier {identifier!r}",
                        f"{kind}:{identifier}",
                        f"Give every {kind} a unique stable ID.",
                    )
                )

    dish_ids = set(event.dish_by_id)
    resource_by_id = event.resource_by_id
    step_counts = Counter(step.dish_id for step in event.preparation)
    order_counts = Counter(step.order for step in event.preparation)

    for order, count in sorted(order_counts.items()):
        if count > 1:
            findings.append(
                _finding(
                    "AG003",
                    Severity.ERROR,
                    f"preparation order {order} is used {count} times",
                    "event.preparation",
                    "Use a unique positive order number for every preparation step.",
                )
            )

    for index, step in enumerate(event.preparation):
        path = f"event.preparation[{index}]"
        if step.order < 1:
            findings.append(
                _finding(
                    "AG004",
                    Severity.ERROR,
                    f"preparation order must be positive, got {step.order}",
                    f"{path}.order",
                    "Number steps from 1 upward.",
                )
            )
        if step.dish_id not in dish_ids:
            findings.append(
                _finding(
                    "AG005",
                    Severity.ERROR,
                    f"preparation step references unknown dish {step.dish_id!r}",
                    f"{path}.dish",
                    "Use a dish ID declared in event.dishes.",
                )
            )
            continue
        dish = event.dish_by_id[step.dish_id]
        for resource_id in step.clean_before:
            resource = resource_by_id.get(resource_id)
            if resource is None:
                findings.append(
                    _finding(
                        "AG006",
                        Severity.ERROR,
                        f"cleaning boundary references unknown resource {resource_id!r}",
                        f"{path}.clean_before",
                        "Declare the resource or remove it from clean_before.",
                    )
                )
            elif resource_id not in dish.prep_resources:
                findings.append(
                    _finding(
                        "AG007",
                        Severity.WARNING,
                        (
                            f"{resource.name!r} is cleaned before {dish.name!r} "
                            "but is not listed as one of that dish's prep resources"
                        ),
                        f"{path}.clean_before",
                        "Check the resource ID or add it to the dish's prep_resources.",
                    )
                )
            elif not resource.cleanable:
                findings.append(
                    _finding(
                        "AG008",
                        Severity.ERROR,
                        f"resource {resource.name!r} is declared non-cleanable",
                        f"{path}.clean_before",
                        "Use a dedicated/replacement resource instead of a cleaning boundary.",
                    )
                )

    resource_usage: dict[str, set[str]] = defaultdict(set)
    for dish_index, dish in enumerate(event.dishes):
        path = f"event.dishes[{dish_index}]"
        if step_counts[dish.dish_id] > 1:
            findings.append(
                _finding(
                    "AG009",
                    Severity.ERROR,
                    f"dish {dish.name!r} has more than one preparation step",
                    "event.preparation",
                    "Represent the dish once and list all of its resources on the dish.",
                )
            )
        if dish.prep_resources and step_counts[dish.dish_id] == 0:
            findings.append(
                _finding(
                    "AG010",
                    Severity.WARNING,
                    f"dish {dish.name!r} uses prep resources but has no preparation order",
                    path,
                    "Add the dish to event.preparation so carry-over risk can be traced.",
                )
            )

        for resource_id in (*dish.prep_resources, *dish.service_resources):
            resource_usage[resource_id].add(dish.dish_id)
            if resource_id not in resource_by_id:
                findings.append(
                    _finding(
                        "AG011",
                        Severity.ERROR,
                        f"dish {dish.name!r} references unknown resource {resource_id!r}",
                        path,
                        "Declare the resource in event.resources or correct the ID.",
                    )
                )

        for ingredient_index, ingredient in enumerate(dish.ingredients):
            ingredient_path = f"{path}.ingredients[{ingredient_index}]"
            overlap = ingredient.contains & ingredient.may_contain
            if overlap:
                findings.append(
                    _finding(
                        "AG012",
                        Severity.ERROR,
                        (
                            f"ingredient {ingredient.name!r} declares the same allergen "
                            f"as contains and may_contain: {', '.join(sorted(overlap))}"
                        ),
                        ingredient_path,
                        "Move each declaration to exactly one certainty category.",
                    )
                )
            if ingredient.verified and not ingredient.evidence:
                findings.append(
                    _finding(
                        "AG013",
                        Severity.ERROR,
                        f"verified ingredient {ingredient.name!r} has no evidence note",
                        f"{ingredient_path}.evidence",
                        "Record what was checked, for example package label plus date.",
                    )
                )
            if not ingredient.verified:
                findings.append(
                    _finding(
                        "AG014",
                        Severity.WARNING,
                        f"ingredient {ingredient.name!r} is not verified",
                        ingredient_path,
                        "Check the current package/recipe and record an evidence note.",
                    )
                )

        direct_conflicts = matching_hazards(dish.contains, dish.free_from)
        if direct_conflicts:
            findings.append(
                _finding(
                    "AG015",
                    Severity.ERROR,
                    (
                        f"dish {dish.name!r} claims free_from but directly contains: "
                        f"{', '.join(direct_conflicts)}"
                    ),
                    f"{path}.free_from",
                    "Remove the claim or correct and re-verify the ingredient declaration.",
                )
            )
        precautionary_conflicts = matching_hazards(dish.may_contain, dish.free_from)
        if precautionary_conflicts:
            findings.append(
                _finding(
                    "AG016",
                    Severity.WARNING,
                    (
                        f"dish {dish.name!r} claims free_from while may_contain lists: "
                        f"{', '.join(precautionary_conflicts)}"
                    ),
                    f"{path}.free_from",
                    "Do not present the free-from claim until the uncertainty is resolved.",
                )
            )

    for resource in event.resources:
        if resource.dedicated_to:
            if resource.dedicated_to not in dish_ids:
                findings.append(
                    _finding(
                        "AG017",
                        Severity.ERROR,
                        (
                            f"resource {resource.name!r} is dedicated to unknown dish "
                            f"{resource.dedicated_to!r}"
                        ),
                        f"resource:{resource.resource_id}.dedicated_to",
                        "Use an existing dish ID.",
                    )
                )
            unexpected = resource_usage[resource.resource_id] - {resource.dedicated_to}
            if unexpected:
                findings.append(
                    _finding(
                        "AG018",
                        Severity.ERROR,
                        (
                            f"dedicated resource {resource.name!r} is also used by: "
                            f"{', '.join(sorted(unexpected))}"
                        ),
                        f"resource:{resource.resource_id}",
                        "Use a different resource or remove the dedicated claim.",
                    )
                )

    return tuple(
        sorted(findings, key=lambda item: (item.severity.value, item.code, item.path, item.message))
    )
