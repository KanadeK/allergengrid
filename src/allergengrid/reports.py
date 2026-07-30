"""Self-contained, print-friendly AllergenGrid reports."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from collections import Counter
from pathlib import Path

from allergengrid import __version__
from allergengrid.models import (
    AnalysisResult,
    Finding,
    Reason,
    Severity,
    Status,
)
from allergengrid.standards import PROFILE_LABELS, REFERENCE_URLS, label

GENERATED_FILES = (
    "analysis.json",
    "kitchen-plan.md",
    "labels.html",
    "matrix.csv",
    "report.html",
    "receipt.json",
    "manifest.sha256",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _reason_data(reason: Reason) -> dict[str, object]:
    return {
        "code": reason.code,
        "category": reason.category,
        "message": reason.message,
        "allergens": list(reason.allergens),
        "source_dish": reason.source_dish,
        "resource": reason.resource,
    }


def _finding_data(finding: Finding) -> dict[str, object]:
    return {
        "code": finding.code,
        "severity": finding.severity.value,
        "message": finding.message,
        "path": finding.path,
        "hint": finding.hint,
    }


def analysis_data(result: AnalysisResult) -> dict[str, object]:
    """Return a stable JSON-compatible analysis document."""

    loaded = result.loaded
    event = loaded.event
    custom_labels = event.custom_allergen_labels
    return {
        "schema_version": 1,
        "tool": {"name": "AllergenGrid", "version": __version__},
        "source": {
            "input_digest": loaded.input_digest,
            "files": loaded.input_hashes,
        },
        "event": {
            "name": event.name,
            "date": event.event_date,
            "revision": event.revision,
            "profile": event.profile,
            "profile_label": PROFILE_LABELS[event.profile],
        },
        "status_meanings": {
            Status.BLOCK.value: "Declared direct conflict. Do not offer for this constraint.",
            Status.HOLD.value: "Uncertainty or cross-contact path requires human resolution.",
            Status.CANDIDATE.value: (
                "No conflict found in the supplied declarations; re-check current labels "
                "and guest needs before service."
            ),
        },
        "guests": [
            {
                "id": guest.guest_id,
                "name": guest.name,
                "avoid_allergens": [
                    {
                        "id": allergen_id,
                        "label": label(allergen_id, custom_labels),
                    }
                    for allergen_id in sorted(guest.avoid_allergens)
                ],
                "required_diets": sorted(guest.required_diets),
                "notes": guest.notes,
            }
            for guest in loaded.guests
        ],
        "dishes": [
            {
                "id": dish.dish_id,
                "name": dish.name,
                "contains": [
                    {"id": allergen_id, "label": label(allergen_id, custom_labels)}
                    for allergen_id in sorted(dish.contains)
                ],
                "may_contain": [
                    {"id": allergen_id, "label": label(allergen_id, custom_labels)}
                    for allergen_id in sorted(dish.may_contain)
                ],
                "free_from": [
                    {"id": allergen_id, "label": label(allergen_id, custom_labels)}
                    for allergen_id in sorted(dish.free_from)
                ],
                "diet_tags": sorted(dish.diet_tags),
                "unverified_ingredients": list(dish.unverified_ingredients),
                "prep_resources": list(dish.prep_resources),
                "service_resources": list(dish.service_resources),
            }
            for dish in event.dishes
        ],
        "assessments": [
            {
                "guest_id": assessment.guest_id,
                "dish_id": assessment.dish_id,
                "status": assessment.status.value,
                "reasons": [_reason_data(reason) for reason in assessment.reasons],
            }
            for assessment in result.assessments
        ],
        "findings": [_finding_data(finding) for finding in result.findings],
        "status_counts": {status.value: result.status_counts.get(status, 0) for status in Status},
        "shared_service_resources": {
            resource_id: list(dish_ids)
            for resource_id, dish_ids in sorted(
                result.cross_contact.shared_service_resources.items()
            )
        },
        "recommended_preparation": [
            {
                "order": step.order,
                "dish_id": step.dish_id,
                "clean_before": list(step.clean_before),
                "replace_resources": list(step.replace_resources),
            }
            for step in result.cross_contact.recommended_steps
        ],
    }


def _status_label(status: Status) -> str:
    return {
        Status.BLOCK: "BLOCK",
        Status.HOLD: "HOLD",
        Status.CANDIDATE: "CANDIDATE",
    }[status]


def _html_list(values: list[str], *, empty: str = "None declared") -> str:
    if not values:
        return f'<span class="muted">{html.escape(empty)}</span>'
    return ", ".join(html.escape(value) for value in values)


def _allergen_labels(result: AnalysisResult, values: frozenset[str] | set[str]) -> list[str]:
    custom = result.loaded.event.custom_allergen_labels
    return [label(value, custom) for value in sorted(values)]


def _render_findings(result: AnalysisResult) -> str:
    if not result.findings:
        return '<p class="empty">No findings.</p>'
    rows: list[str] = []
    for finding in result.findings:
        rows.append(
            '<li class="finding '
            f'{finding.severity.value}">'
            f'<div><span class="severity">{html.escape(finding.severity.value.upper())}</span> '
            f"<code>{html.escape(finding.code)}</code> "
            f"<strong>{html.escape(finding.message)}</strong></div>"
            f'<div class="path">{html.escape(finding.path)}</div>'
            f'<div class="hint">{html.escape(finding.hint)}</div>'
            "</li>"
        )
    return '<ol class="findings">' + "".join(rows) + "</ol>"


def _render_matrix(result: AnalysisResult) -> str:
    event = result.loaded.event
    headings = "".join(f'<th scope="col">{html.escape(dish.name)}</th>' for dish in event.dishes)
    rows: list[str] = []
    for guest in result.loaded.guests:
        cells: list[str] = []
        for dish in event.dishes:
            assessment = result.assessment_for(guest.guest_id, dish.dish_id)
            reason_text = "; ".join(reason.message for reason in assessment.reasons)
            details = (
                f'<span class="reason-count">{len(assessment.reasons)} reason'
                f"{'s' if len(assessment.reasons) != 1 else ''}</span>"
                if assessment.reasons
                else '<span class="reason-count">declared inputs clear</span>'
            )
            cells.append(
                f'<td class="status {assessment.status.value}" '
                f'title="{html.escape(reason_text, quote=True)}">'
                f"<strong>{_status_label(assessment.status)}</strong>{details}</td>"
            )
        constraints = [
            *(_allergen_labels(result, guest.avoid_allergens)),
            *(sorted(guest.required_diets)),
        ]
        rows.append(
            "<tr>"
            f'<th scope="row">{html.escape(guest.name)}'
            f'<span class="constraints">{_html_list(constraints, empty="No constraints")}</span>'
            "</th>" + "".join(cells) + "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="matrix"><thead><tr>'
        '<th scope="col">Guest / constraints</th>'
        f"{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _render_dishes(result: AnalysisResult) -> str:
    rows: list[str] = []
    for dish in result.loaded.event.dishes:
        cross = result.cross_contact.reasons_by_dish[dish.dish_id]
        cross_allergens = {allergen_id for reason in cross for allergen_id in reason.allergens}
        unknown_cross = any(not reason.allergens for reason in cross)
        cross_labels = _allergen_labels(result, cross_allergens)
        if unknown_cross:
            cross_labels.append("Unknown carry-over")
        ingredient_evidence = "".join(
            "<li>"
            f"<strong>{html.escape(ingredient.name)}</strong>: "
            f"{html.escape(ingredient.evidence) if ingredient.evidence else 'NOT VERIFIED'}"
            "</li>"
            for ingredient in dish.ingredients
        )
        rows.append(
            '<article class="dish-card">'
            f"<h3>{html.escape(dish.name)}</h3>"
            '<dl class="facts">'
            f"<dt>Contains</dt><dd>{_html_list(_allergen_labels(result, dish.contains))}</dd>"
            f"<dt>May contain</dt><dd>{_html_list(_allergen_labels(result, dish.may_contain))}</dd>"
            f"<dt>Resource carry-over</dt><dd>{_html_list(cross_labels)}</dd>"
            f"<dt>Diet tags</dt><dd>{_html_list(sorted(dish.diet_tags))}</dd>"
            f"<dt>Free-from claims supplied</dt>"
            f"<dd>{_html_list(_allergen_labels(result, dish.free_from))}</dd>"
            "</dl>"
            "<details><summary>Ingredient evidence</summary>"
            f"<ul>{ingredient_evidence}</ul></details>"
            "</article>"
        )
    return '<div class="dish-grid">' + "".join(rows) + "</div>"


def _render_declared_plan(result: AnalysisResult) -> str:
    event = result.loaded.event
    if not event.preparation:
        return '<p class="empty">No declared preparation order.</p>'
    items: list[str] = []
    for step in sorted(event.preparation, key=lambda value: (value.order, value.dish_id)):
        dish = event.dish_by_id.get(step.dish_id)
        dish_name = dish.name if dish else step.dish_id
        cleaning = (
            f"Clean first: {', '.join(step.clean_before)}."
            if step.clean_before
            else "No cleaning boundary declared."
        )
        note = f" {step.note}" if step.note else ""
        items.append(
            f"<li><strong>{step.order}. {html.escape(dish_name)}</strong>"
            f"<span>{html.escape(cleaning + note)}</span></li>"
        )
    return '<ol class="plan">' + "".join(items) + "</ol>"


def _render_recommended_plan(result: AnalysisResult) -> str:
    event = result.loaded.event
    items: list[str] = []
    for step in result.cross_contact.recommended_steps:
        dish = event.dish_by_id[step.dish_id]
        actions: list[str] = []
        if step.clean_before:
            actions.append(f"clean: {', '.join(step.clean_before)}")
        if step.replace_resources:
            actions.append(f"replace/dedicate: {', '.join(step.replace_resources)}")
        if not actions:
            actions.append("no new boundary proposed")
        items.append(
            f"<li><strong>{step.order}. {html.escape(dish.name)}</strong>"
            f"<span>{html.escape('; '.join(actions))}</span></li>"
        )
    return '<ol class="plan">' + "".join(items) + "</ol>"


def render_report(result: AnalysisResult) -> str:
    """Render one accessible, self-contained HTML report."""

    event = result.loaded.event
    counts = result.status_counts
    finding_counts = Counter(finding.severity for finding in result.findings)
    title = f"{event.name} — AllergenGrid report"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17201d;
      --muted: #5d6b65;
      --paper: #f7f7f2;
      --card: #ffffff;
      --line: #ccd4cf;
      --accent: #145c52;
      --candidate: #d9eee8;
      --candidate-ink: #0c5147;
      --hold: #fff1c7;
      --hold-ink: #765500;
      --block: #ffe0dc;
      --block-ink: #8f211b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto 80px; }}
    header {{ padding: 56px 0 30px; border-bottom: 1px solid var(--line); }}
    h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 5vw, 4.4rem); letter-spacing: -0.055em; }}
    h2 {{ margin-top: 48px; font-size: 1.55rem; }}
    h3 {{ margin-top: 0; }}
    .eyebrow {{ color: var(--accent); font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }}
    .lede {{ max-width: 780px; color: var(--muted); font-size: 1.08rem; }}
    .meta, .stats {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }}
    .pill {{ border: 1px solid var(--line); background: var(--card); border-radius: 999px; padding: 7px 11px; }}
    .stats {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); margin: 30px 0; }}
    .stat {{ background: var(--card); border: 1px solid var(--line); padding: 18px; border-radius: 14px; }}
    .stat strong {{ display: block; font-size: 1.8rem; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 14px; background: var(--card); }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--line); border-right: 1px solid var(--line); padding: 13px; vertical-align: top; }}
    th {{ text-align: left; background: #eef1ed; }}
    tr:last-child th, tr:last-child td {{ border-bottom: 0; }}
    th:last-child, td:last-child {{ border-right: 0; }}
    .constraints, .reason-count {{ display: block; margin-top: 5px; color: var(--muted); font-size: .78rem; font-weight: 500; }}
    .status strong {{ display: block; }}
    .status.candidate {{ background: var(--candidate); color: var(--candidate-ink); }}
    .status.hold {{ background: var(--hold); color: var(--hold-ink); }}
    .status.block {{ background: var(--block); color: var(--block-ink); }}
    .dish-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; }}
    .dish-card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 20px; }}
    .facts {{ display: grid; grid-template-columns: minmax(120px, .8fr) 1.5fr; gap: 8px 12px; }}
    .facts dt {{ color: var(--muted); font-weight: 700; }}
    .facts dd {{ margin: 0; }}
    .findings {{ list-style: none; padding: 0; }}
    .finding {{ background: var(--card); border: 1px solid var(--line); border-left-width: 5px; border-radius: 10px; padding: 14px; margin: 10px 0; }}
    .finding.error {{ border-left-color: var(--block-ink); }}
    .finding.warning {{ border-left-color: #b57c00; }}
    .severity {{ font-weight: 850; font-size: .78rem; }}
    .path, .hint {{ margin-top: 4px; color: var(--muted); }}
    .plan {{ padding-left: 24px; }}
    .plan li {{ margin: 9px 0; }}
    .plan span {{ display: block; color: var(--muted); }}
    .notice {{ border: 2px solid var(--accent); background: #e8f3f0; padding: 18px; border-radius: 12px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .digest {{ overflow-wrap: anywhere; }}
    .muted, .empty {{ color: var(--muted); }}
    footer {{ margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: .9rem; }}
    @media (max-width: 760px) {{
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
      main {{ width: min(100% - 20px, 1180px); }}
    }}
    @media print {{
      body {{ background: #fff; font-size: 10pt; }}
      main {{ width: 100%; margin: 0; }}
      header {{ padding-top: 0; }}
      .dish-card, .finding, .table-wrap {{ break-inside: avoid; }}
      details {{ open: true; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">AllergenGrid / declaration audit</div>
    <h1>{html.escape(event.name)}</h1>
    <p class="lede">A deterministic view of the declarations supplied by the organizer.
    CANDIDATE never means medically safe; labels, recipes, preparation, service setup, and
    each guest's current needs still require human confirmation.</p>
    <div class="meta">
      <span class="pill">Date: {html.escape(event.event_date)}</span>
      <span class="pill">Revision: {html.escape(event.revision)}</span>
      <span class="pill">Profile: {html.escape(PROFILE_LABELS[event.profile])}</span>
    </div>
  </header>

  <section aria-labelledby="summary">
    <h2 id="summary">Decision summary</h2>
    <div class="notice"><strong>Interpretation:</strong> BLOCK = direct declared conflict;
    HOLD = uncertainty or cross-contact must be resolved; CANDIDATE = no conflict was found
    in the supplied data, not a safety guarantee.</div>
    <div class="stats">
      <div class="stat"><strong>{counts.get(Status.CANDIDATE, 0)}</strong>candidate cells</div>
      <div class="stat"><strong>{counts.get(Status.HOLD, 0)}</strong>hold cells</div>
      <div class="stat"><strong>{counts.get(Status.BLOCK, 0)}</strong>blocked cells</div>
      <div class="stat"><strong>{finding_counts.get(Severity.ERROR, 0)}</strong>errors</div>
      <div class="stat"><strong>{finding_counts.get(Severity.WARNING, 0)}</strong>warnings</div>
    </div>
    {_render_matrix(result)}
  </section>

  <section aria-labelledby="dishes">
    <h2 id="dishes">Dish declarations and evidence</h2>
    {_render_dishes(result)}
  </section>

  <section aria-labelledby="declared-plan">
    <h2 id="declared-plan">Declared preparation order</h2>
    {_render_declared_plan(result)}
  </section>

  <section aria-labelledby="draft-plan">
    <h2 id="draft-plan">Risk-reduction draft</h2>
    <p class="muted">Allergen-light-to-heavy ordering generated from declared data. This is
    a review aid, not a sanitation procedure or a replacement for trained staff.</p>
    {_render_recommended_plan(result)}
  </section>

  <section aria-labelledby="findings">
    <h2 id="findings">Findings and repair actions</h2>
    {_render_findings(result)}
  </section>

  <footer>
    <p>Generated by AllergenGrid {html.escape(__version__)}. Input digest:
    <code class="digest">{html.escape(result.loaded.input_digest)}</code>.</p>
    <p>Reference profiles:
      <a href="{html.escape(REFERENCE_URLS["us"])}">FDA major allergens</a>,
      <a href="{html.escape(REFERENCE_URLS["eu"])}">EU regulated allergens</a>, and
      <a href="{html.escape(REFERENCE_URLS["cross_contact"])}">CDC restaurant practices</a>.
      Check the current authority applicable to your location.</p>
  </footer>
</main>
</body>
</html>
"""


def render_labels(result: AnalysisResult) -> str:
    """Render print cards that preserve uncertainty."""

    cards: list[str] = []
    for dish in result.loaded.event.dishes:
        cross = result.cross_contact.reasons_by_dish[dish.dish_id]
        cross_allergens = {allergen_id for reason in cross for allergen_id in reason.allergens}
        unknown_cross = any(not reason.allergens for reason in cross)
        warnings: list[str] = []
        if dish.has_unverified_ingredients:
            warnings.append("UNVERIFIED: " + ", ".join(dish.unverified_ingredients))
        if unknown_cross:
            warnings.append("UNKNOWN RESOURCE CARRY-OVER")
        warning_html = "".join(
            f'<p class="warning">{html.escape(warning)}</p>' for warning in warnings
        )
        cards.append(
            '<article class="label">'
            f"<h2>{html.escape(dish.name)}</h2>"
            f"<p><strong>Contains:</strong> "
            f"{_html_list(_allergen_labels(result, dish.contains))}</p>"
            f"<p><strong>May contain:</strong> "
            f"{_html_list(_allergen_labels(result, dish.may_contain))}</p>"
            f"<p><strong>Resource carry-over:</strong> "
            f"{_html_list(_allergen_labels(result, cross_allergens))}</p>"
            f"<p><strong>Diet tags:</strong> {_html_list(sorted(dish.diet_tags))}</p>"
            f"{warning_html}"
            '<p class="check">CHECK CURRENT LABELS + PREP SETUP BEFORE SERVICE</p>'
            "</article>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(result.loaded.event.name)} — dish cards</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font: 14px/1.4 system-ui, sans-serif; margin: 20px; color: #111; }}
    main {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
    .label {{ border: 2px solid #111; padding: 15px; break-inside: avoid; min-height: 240px; }}
    h2 {{ margin: 0 0 10px; }}
    p {{ margin: 7px 0; }}
    .warning {{ background: #fff1c7; border-left: 5px solid #8a6200; padding: 7px; }}
    .check {{ border-top: 1px solid #111; padding-top: 9px; font-weight: 800; }}
    .muted {{ color: #555; }}
    @media (max-width: 650px) {{ main {{ grid-template-columns: 1fr; }} }}
    @media print {{ body {{ margin: 0; }} }}
  </style>
</head>
<body>
<main>{"".join(cards)}</main>
</body>
</html>
"""


def _csv_safe(value: str) -> str:
    """Neutralize spreadsheet formulas while preserving the visible value."""

    if value.startswith(("\t", "\r", "=", "+", "-", "@")):
        return "'" + value
    return value


def render_matrix_csv(result: AnalysisResult) -> str:
    """Render a wide, spreadsheet-safe guest/dish matrix."""

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        ["guest_id", "guest_name", "constraints"]
        + [_csv_safe(dish.name) for dish in result.loaded.event.dishes]
    )
    for guest in result.loaded.guests:
        constraints = "|".join([*sorted(guest.avoid_allergens), *sorted(guest.required_diets)])
        writer.writerow(
            [
                _csv_safe(guest.guest_id),
                _csv_safe(guest.name),
                _csv_safe(constraints),
                *[
                    result.assessment_for(guest.guest_id, dish.dish_id).status.value
                    for dish in result.loaded.event.dishes
                ],
            ]
        )
    return output.getvalue()


def render_kitchen_plan(result: AnalysisResult) -> str:
    """Render a plain Markdown handoff for kitchen staff review."""

    event = result.loaded.event
    lines = [
        f"# {event.name} — kitchen review",
        "",
        "> Review aid only. CANDIDATE is not a safety guarantee. Confirm current labels,",
        "> recipes, cleaning, service setup, and each guest's needs before service.",
        "",
        f"- Event date: {event.event_date}",
        f"- Revision: {event.revision}",
        f"- Input digest: `{result.loaded.input_digest}`",
        "",
        "## Declared preparation order",
        "",
    ]
    if event.preparation:
        for declared_step in sorted(
            event.preparation, key=lambda value: (value.order, value.dish_id)
        ):
            dish = event.dish_by_id.get(declared_step.dish_id)
            dish_name = dish.name if dish else declared_step.dish_id
            lines.append(f"{declared_step.order}. **{dish_name}**")
            lines.append(
                "   - Clean before: "
                + (
                    ", ".join(declared_step.clean_before)
                    if declared_step.clean_before
                    else "none declared"
                )
            )
            if declared_step.note:
                lines.append(f"   - Note: {declared_step.note}")
    else:
        lines.append("No order declared.")

    lines.extend(["", "## Risk-reduction draft", ""])
    for recommended_step in result.cross_contact.recommended_steps:
        dish = event.dish_by_id[recommended_step.dish_id]
        lines.append(f"{recommended_step.order}. **{dish.name}**")
        lines.append(
            "   - Clean before: "
            + (
                ", ".join(recommended_step.clean_before)
                if recommended_step.clean_before
                else "none proposed"
            )
        )
        lines.append(
            "   - Replace/dedicate: "
            + (
                ", ".join(recommended_step.replace_resources)
                if recommended_step.replace_resources
                else "none proposed"
            )
        )

    lines.extend(["", "## Shared service resources", ""])
    if result.cross_contact.shared_service_resources:
        for resource_id, dish_ids in sorted(result.cross_contact.shared_service_resources.items()):
            lines.append(f"- **{resource_id}**: {', '.join(dish_ids)}")
            lines.append("  - Action: assign a dedicated utensil/container per dish.")
    else:
        lines.append("No shared service resources declared.")

    lines.extend(["", "## Findings", ""])
    if result.findings:
        for finding in result.findings:
            lines.append(
                f"- **{finding.severity.value.upper()} {finding.code}** "
                f"`{finding.path}` — {finding.message}"
            )
            lines.append(f"  - Repair: {finding.hint}")
    else:
        lines.append("No findings.")
    return "\n".join(lines) + "\n"


def build_outputs(result: AnalysisResult, output_dir: str | Path) -> dict[str, Path]:
    """Write all deterministic report files and return their paths."""

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    analysis_document = analysis_data(result)
    content: dict[str, bytes] = {
        "analysis.json": _canonical_json(analysis_document).encode("utf-8"),
        "kitchen-plan.md": render_kitchen_plan(result).encode("utf-8"),
        "labels.html": render_labels(result).encode("utf-8"),
        "matrix.csv": render_matrix_csv(result).encode("utf-8-sig"),
        "report.html": render_report(result).encode("utf-8"),
    }
    primary_hashes = {name: _sha256(data) for name, data in sorted(content.items())}
    analysis_digest = _sha256(content["analysis.json"])
    receipt: dict[str, object] = {
        "schema_version": 1,
        "tool": {"name": "AllergenGrid", "version": __version__},
        "event": {
            "name": result.loaded.event.name,
            "date": result.loaded.event.event_date,
            "revision": result.loaded.event.revision,
        },
        "input_digest": result.loaded.input_digest,
        "input_files": result.loaded.input_hashes,
        "analysis_digest": analysis_digest,
        "output_files": primary_hashes,
        "status_counts": {status.value: result.status_counts.get(status, 0) for status in Status},
        "finding_counts": {
            severity.value: sum(1 for finding in result.findings if finding.severity is severity)
            for severity in Severity
        },
        "disclaimer": (
            "This receipt proves byte consistency for supplied declarations and generated "
            "outputs. It does not certify food safety or legal/regulatory compliance."
        ),
    }
    content["receipt.json"] = _canonical_json(receipt).encode("utf-8")
    manifest_lines = [f"{_sha256(data)}  {name}" for name, data in sorted(content.items())]
    content["manifest.sha256"] = ("\n".join(manifest_lines) + "\n").encode("utf-8")

    paths: dict[str, Path] = {}
    for name, data in content.items():
        path = destination / name
        path.write_bytes(data)
        paths[name] = path
    return paths
