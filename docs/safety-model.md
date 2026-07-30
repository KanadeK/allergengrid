# Safety model and limitations

AllergenGrid is intentionally conservative, but it cannot make food safe.

## The central rule

`CANDIDATE` means:

> No conflict was found in the explicit declarations supplied to this run.

It does **not** mean:

- medically safe;
- allergen-free;
- compliant with a law or food code;
- suitable for a specific person;
- free from cross-contact outside the modeled resources;
- verified by a regulator, clinician, or trained food-safety professional.

## What the model trusts

The program only trusts structured declarations:

- guest avoid lists and required diet tags;
- ingredient `contains` and `may_contain` fields;
- the organizer's `verified` flag and evidence note;
- resource IDs, declared preparation order, and cleaning boundaries;
- dedicated-resource declarations.

Free-text notes never change a result.

## What the model refuses to infer

AllergenGrid does not infer that:

- "whey" means milk;
- "tahini" means sesame;
- a dish name implies its ingredients;
- vegan automatically means free of a specific allergen;
- a clean-looking utensil has been safely sanitized;
- absence of `may contain` means absence of cross-contact;
- an old package label still matches a current product.

Those facts may be true in a particular case, but accepting them requires a
current source and human review. Record the resulting declaration explicitly.

The loader only normalizes direct naming aliases, such as `eggs` to `egg`. The
US `wheat` and EU `gluten_cereals` categories are treated as conservatively
overlapping; this is category matching, not ingredient inference.

## Unknown-state behavior

For a constrained guest:

- direct overlap becomes `BLOCK`;
- `may_contain` overlap becomes `HOLD`;
- resource carry-over becomes `HOLD`;
- missing required diet tag becomes `HOLD`;
- any unverified ingredient becomes `HOLD`;
- an unknown prior ingredient carried through a resource becomes `HOLD`.

An unresolved `free_from` contradiction is an error.

## Cross-contact model boundaries

The resource tracer is only as complete as the event definition. It can model:

- boards, knives, bowls, pots, appliances, oil, and other preparation resources;
- declared cleaning boundaries for cleanable resources;
- non-cleanable resources that require replacement/dedication;
- dedicated resources;
- buffet utensils and containers shared by more than one dish.

It does not observe:

- hands, gloves, clothing, towels, airborne particles, spills, storage, or
  supplier facilities unless the organizer models them as resources/declarations;
- whether a stated cleaning procedure was performed correctly;
- guest behavior at a buffet;
- undeclared substitutions;
- allergen concentration or reaction severity.

When a path is missing, add it to the case. Do not reinterpret a missing path as
evidence of safety.

## Regulatory profiles

The built-in profiles are convenience declaration sets, not compliance modes.
They are sourced from:

- [FDA major allergens](https://www.fda.gov/consumers/consumer-updates/have-food-allergies-read-label);
- [EU regulated allergens](https://food.ec.europa.eu/food-safety/campaign-2026/allergies_en).

Local rules, exemptions, thresholds, definitions, and required communications
can differ. Check the authority applicable to the event.

## Privacy

Guest allergy and dietary data can be sensitive.

- Use stable pseudonymous IDs when names are unnecessary.
- Keep case directories and generated packs access-controlled.
- Do not upload real data to public issues.
- Delete or retain event data according to a documented local policy.
- The tool does not phone home, but normal operating-system backups and sync
  tools may still copy files.

## Integrity

SHA-256 manifests prove byte consistency between a package and its manifest.
They do not prove:

- who authored the declarations;
- that an event happened as described;
- that a timestamp is externally trusted;
- that the source labels were accurate;
- that a person followed the plan.

Use signed organizational records or a trusted timestamping/signature system if
authorship and time need independent proof.
