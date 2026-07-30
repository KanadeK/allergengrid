"""Deterministic guest, dish, and cross-contact analysis."""

from __future__ import annotations

from collections import Counter

from allergengrid.cross_contact import analyze_cross_contact
from allergengrid.models import (
    AnalysisResult,
    Assessment,
    Finding,
    LoadedCase,
    Reason,
    Severity,
    Status,
)
from allergengrid.standards import matching_hazards
from allergengrid.validation import validate_case


def _cross_findings(
    loaded: LoadedCase,
    reasons_by_dish: dict[str, tuple[Reason, ...]],
    shared_service: dict[str, tuple[str, ...]],
) -> list[Finding]:
    event = loaded.event
    findings: list[Finding] = []
    for dish in event.dishes:
        reasons = reasons_by_dish[dish.dish_id]
        prep_resources = sorted(
            reason.resource
            for reason in reasons
            if reason.category == "prep_cross_contact" and reason.resource is not None
        )
        service_resources = sorted(
            reason.resource
            for reason in reasons
            if reason.category == "service_cross_contact" and reason.resource is not None
        )
        if prep_resources:
            findings.append(
                Finding(
                    code="AG201",
                    severity=Severity.WARNING,
                    message=(
                        f"{dish.name!r} has preparation carry-over risk through: "
                        f"{', '.join(prep_resources)}"
                    ),
                    path=f"dish:{dish.dish_id}.prep_resources",
                    hint="Add a verified cleaning boundary, replace the resource, or dedicate it.",
                )
            )
        if service_resources:
            findings.append(
                Finding(
                    code="AG202",
                    severity=Severity.WARNING,
                    message=(
                        f"{dish.name!r} has shared-service risk through: "
                        f"{', '.join(service_resources)}"
                    ),
                    path=f"dish:{dish.dish_id}.service_resources",
                    hint="Give every dish a dedicated serving utensil or container.",
                )
            )
        cross_allergens = {allergen for reason in reasons for allergen in reason.allergens}
        claim_conflicts = matching_hazards(cross_allergens, dish.free_from)
        if claim_conflicts or (dish.free_from and any(not reason.allergens for reason in reasons)):
            findings.append(
                Finding(
                    code="AG203",
                    severity=Severity.ERROR,
                    message=(
                        f"{dish.name!r} has a free-from claim invalidated by declared "
                        "resource reuse or an unknown carry-over"
                    ),
                    path=f"dish:{dish.dish_id}.free_from",
                    hint="Resolve the resource risk before using the free-from claim.",
                )
            )
    for resource_id, dish_ids in sorted(shared_service.items()):
        findings.append(
            Finding(
                code="AG204",
                severity=Severity.WARNING,
                message=(f"service resource {resource_id!r} is shared by {', '.join(dish_ids)}"),
                path=f"resource:{resource_id}",
                hint="Assign a unique serving resource to each dish.",
            )
        )
    return findings


def _assess(
    loaded: LoadedCase, guest_id: str, dish_id: str, cross: tuple[Reason, ...]
) -> Assessment:
    event = loaded.event
    guest = next(guest for guest in loaded.guests if guest.guest_id == guest_id)
    dish = event.dish_by_id[dish_id]
    reasons: list[Reason] = []

    direct = matching_hazards(dish.contains, guest.avoid_allergens)
    if direct:
        reasons.append(
            Reason(
                code="DIRECT_CONTAINS",
                category="direct",
                message=f"directly contains: {', '.join(direct)}",
                allergens=direct,
            )
        )

    precautionary = matching_hazards(dish.may_contain, guest.avoid_allergens)
    if precautionary:
        reasons.append(
            Reason(
                code="MAY_CONTAIN",
                category="precautionary",
                message=f"may contain: {', '.join(precautionary)}",
                allergens=precautionary,
            )
        )

    for reason in cross:
        hits = matching_hazards(reason.allergens, guest.avoid_allergens)
        if hits:
            reasons.append(
                Reason(
                    code=reason.code,
                    category=reason.category,
                    message=reason.message,
                    allergens=hits,
                    source_dish=reason.source_dish,
                    resource=reason.resource,
                )
            )
        elif not reason.allergens and (guest.avoid_allergens or guest.required_diets):
            reasons.append(reason)

    missing_diets = tuple(sorted(guest.required_diets - dish.diet_tags))
    if missing_diets:
        reasons.append(
            Reason(
                code="DIET_NOT_DECLARED",
                category="diet",
                message=f"required diet tag not declared: {', '.join(missing_diets)}",
            )
        )

    if dish.has_unverified_ingredients and (guest.avoid_allergens or guest.required_diets):
        reasons.append(
            Reason(
                code="UNVERIFIED_INGREDIENT",
                category="source_quality",
                message=(f"unverified ingredients: {', '.join(dish.unverified_ingredients)}"),
            )
        )

    if direct:
        status = Status.BLOCK
    elif reasons:
        status = Status.HOLD
    else:
        status = Status.CANDIDATE
    return Assessment(
        guest_id=guest_id,
        dish_id=dish_id,
        status=status,
        reasons=tuple(
            sorted(
                reasons,
                key=lambda reason: (
                    reason.category,
                    reason.code,
                    reason.resource or "",
                    reason.source_dish or "",
                ),
            )
        ),
    )


def analyze_case(loaded: LoadedCase) -> AnalysisResult:
    """Analyze a loaded case without mutating inputs or consulting a network."""

    cross = analyze_cross_contact(loaded.event)
    findings = list(validate_case(loaded))
    findings.extend(
        _cross_findings(
            loaded,
            cross.reasons_by_dish,
            cross.shared_service_resources,
        )
    )
    assessments = tuple(
        _assess(
            loaded,
            guest.guest_id,
            dish.dish_id,
            cross.reasons_by_dish[dish.dish_id],
        )
        for guest in loaded.guests
        for dish in loaded.event.dishes
    )

    for guest in loaded.guests:
        candidates = [
            assessment
            for assessment in assessments
            if assessment.guest_id == guest.guest_id and assessment.status is Status.CANDIDATE
        ]
        if not candidates:
            findings.append(
                Finding(
                    code="AG301",
                    severity=Severity.ERROR,
                    message=f"guest {guest.name!r} has no candidate dish",
                    path=f"guest:{guest.guest_id}",
                    hint=(
                        "Add and verify an option, resolve hold reasons, or contact the guest "
                        "before the event."
                    ),
                )
            )

    status_counts = Counter(assessment.status for assessment in assessments)
    return AnalysisResult(
        loaded=loaded,
        findings=tuple(
            sorted(
                findings,
                key=lambda item: (
                    {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}[item.severity],
                    item.code,
                    item.path,
                    item.message,
                ),
            )
        ),
        assessments=assessments,
        cross_contact=cross,
        status_counts={status: status_counts.get(status, 0) for status in Status},
    )
