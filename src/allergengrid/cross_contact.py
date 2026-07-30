"""Trace cross-contact through declared preparation and service resources."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from allergengrid.models import (
    CrossContactResult,
    Event,
    Reason,
    RecommendedStep,
)


@dataclass(frozen=True, slots=True)
class _Exposure:
    allergen: str | None
    source_dish: str
    certainty: str


def _exposures_for_dish(event: Event, dish_id: str) -> tuple[_Exposure, ...]:
    dish = event.dish_by_id[dish_id]
    exposures = [
        _Exposure(allergen=allergen, source_dish=dish_id, certainty="contains")
        for allergen in sorted(dish.contains)
    ]
    exposures.extend(
        _Exposure(allergen=allergen, source_dish=dish_id, certainty="may_contain")
        for allergen in sorted(dish.may_contain)
    )
    if dish.has_unverified_ingredients:
        exposures.append(_Exposure(allergen=None, source_dish=dish_id, certainty="unknown"))
    return tuple(exposures)


def _reason_from_exposure(
    exposure: _Exposure,
    *,
    target_dish: str,
    resource_id: str,
    service: bool,
) -> Reason:
    prefix = "SERVICE" if service else "PREP"
    source_kind = exposure.certainty.upper()
    if exposure.allergen is None:
        message = (
            f"{target_dish!r} shares {resource_id!r} with {exposure.source_dish!r}, "
            "which has unverified ingredient declarations"
        )
        allergens: tuple[str, ...] = ()
    else:
        message = (
            f"{target_dish!r} can receive {exposure.allergen!r} via {resource_id!r} "
            f"from {exposure.source_dish!r} ({exposure.certainty})"
        )
        allergens = (exposure.allergen,)
    return Reason(
        code=f"{prefix}_{source_kind}",
        category="service_cross_contact" if service else "prep_cross_contact",
        message=message,
        allergens=allergens,
        source_dish=exposure.source_dish,
        resource=resource_id,
    )


def _deduplicate(reasons: list[Reason]) -> tuple[Reason, ...]:
    unique: dict[
        tuple[str, tuple[str, ...], str | None, str | None],
        Reason,
    ] = {}
    for reason in reasons:
        key = (reason.code, reason.allergens, reason.source_dish, reason.resource)
        unique[key] = reason
    return tuple(
        sorted(
            unique.values(),
            key=lambda reason: (
                reason.category,
                reason.resource or "",
                reason.source_dish or "",
                reason.allergens,
                reason.code,
            ),
        )
    )


def _recommend_steps(event: Event) -> tuple[RecommendedStep, ...]:
    """Draft an allergen-light-to-heavy order with explicit cleaning boundaries."""

    resource_by_id = event.resource_by_id

    def score(dish_id: str) -> tuple[int, int, str]:
        dish = event.dish_by_id[dish_id]
        return (
            1 if dish.has_unverified_ingredients else 0,
            len(dish.contains | dish.may_contain),
            dish.dish_id,
        )

    ordered = sorted((dish.dish_id for dish in event.dishes), key=score)
    state: dict[str, set[str | None]] = defaultdict(set)
    recommendations: list[RecommendedStep] = []
    for order, dish_id in enumerate(ordered, start=1):
        dish = event.dish_by_id[dish_id]
        current: set[str | None] = set(dish.contains | dish.may_contain)
        if dish.has_unverified_ingredients:
            current.add(None)
        clean_before: list[str] = []
        replace_resources: list[str] = []
        for resource_id in dish.prep_resources:
            previous = state[resource_id]
            carry_not_already_declared = previous - current
            if carry_not_already_declared:
                resource = resource_by_id.get(resource_id)
                if resource and resource.cleanable:
                    clean_before.append(resource_id)
                    state[resource_id].clear()
                else:
                    replace_resources.append(resource_id)
            state[resource_id].update(current)
        recommendations.append(
            RecommendedStep(
                order=order,
                dish_id=dish_id,
                clean_before=tuple(sorted(clean_before)),
                replace_resources=tuple(sorted(replace_resources)),
            )
        )
    return tuple(recommendations)


def analyze_cross_contact(event: Event) -> CrossContactResult:
    """Build deterministic cross-contact reason paths from explicit resource use."""

    reasons: dict[str, list[Reason]] = defaultdict(list)
    state: dict[str, list[_Exposure]] = defaultdict(list)
    resource_by_id = event.resource_by_id

    for step in sorted(event.preparation, key=lambda item: (item.order, item.dish_id)):
        dish = event.dish_by_id.get(step.dish_id)
        if dish is None:
            continue
        for resource_id in step.clean_before:
            resource = resource_by_id.get(resource_id)
            if resource and resource.cleanable:
                state[resource_id].clear()
        current_exposures = _exposures_for_dish(event, dish.dish_id)
        for resource_id in dish.prep_resources:
            resource = resource_by_id.get(resource_id)
            if resource is None:
                continue
            if resource.dedicated_to == dish.dish_id:
                state[resource_id] = list(current_exposures)
                continue
            for exposure in state[resource_id]:
                if exposure.source_dish == dish.dish_id:
                    continue
                if exposure.allergen is not None and exposure.allergen in dish.contains:
                    continue
                reasons[dish.dish_id].append(
                    _reason_from_exposure(
                        exposure,
                        target_dish=dish.dish_id,
                        resource_id=resource_id,
                        service=False,
                    )
                )
            state[resource_id].extend(current_exposures)

    service_users: dict[str, list[str]] = defaultdict(list)
    for dish in event.dishes:
        for resource_id in dish.service_resources:
            service_users[resource_id].append(dish.dish_id)

    shared_service = {
        resource_id: tuple(sorted(set(dish_ids)))
        for resource_id, dish_ids in service_users.items()
        if len(set(dish_ids)) > 1
    }
    for resource_id, dish_ids in sorted(shared_service.items()):
        resource = resource_by_id.get(resource_id)
        for target_dish in dish_ids:
            if resource and resource.dedicated_to == target_dish:
                continue
            target = event.dish_by_id[target_dish]
            for source_dish in dish_ids:
                if source_dish == target_dish:
                    continue
                for exposure in _exposures_for_dish(event, source_dish):
                    if exposure.allergen is not None and exposure.allergen in target.contains:
                        continue
                    reasons[target_dish].append(
                        _reason_from_exposure(
                            exposure,
                            target_dish=target_dish,
                            resource_id=resource_id,
                            service=True,
                        )
                    )

    return CrossContactResult(
        reasons_by_dish={
            dish.dish_id: _deduplicate(reasons[dish.dish_id]) for dish in event.dishes
        },
        shared_service_resources=shared_service,
        recommended_steps=_recommend_steps(event),
    )
