# Input format

An AllergenGrid case is a directory containing exactly two required source
files:

```text
case/
├── event.json
└── guests.csv
```

Additional files are ignored by the core. The portable pack contains only the
two required inputs and generated reports.

## `event.json`

Top-level fields:

| Field | Type | Requirement |
| --- | --- | --- |
| `schema_version` | integer | Must be `1` |
| `name` | string | Human event name |
| `date` | string | ISO date `YYYY-MM-DD` |
| `revision` | string | Organizer-controlled immutable revision label |
| `profile` | string | `us`, `eu`, or `global` |
| `custom_allergens` | array | Optional explicit IDs and labels |
| `resources` | array | Physical preparation/service resources |
| `dishes` | array | One or more dishes |
| `preparation` | array | Ordered preparation steps |

### Standard profiles

`us`:

```text
milk, egg, fish, crustaceans, tree_nuts, wheat, peanut, soy, sesame
```

`eu`:

```text
gluten_cereals, crustaceans, egg, fish, peanut, soy, milk, tree_nuts,
celery, mustard, sesame, sulphites, lupin, molluscs
```

`global` is the union.

Custom declarations:

```json
{
  "custom_allergens": [
    {"id": "allium", "label": "Allium"}
  ]
}
```

Custom IDs use lowercase letters, digits, and underscores. Standard IDs cannot
be redefined.

### Ingredients

```json
{
  "name": "Plain yogurt",
  "contains": ["milk"],
  "may_contain": [],
  "verified": true,
  "evidence": "Current tub label checked 2026-07-29"
}
```

- `contains` and `may_contain` must not overlap.
- `verified: true` requires a non-empty evidence note.
- `verified: false` creates a warning and holds constrained guest/dish cells.
- `evidence` is not parsed; it is preserved for human review.

### Dishes

```json
{
  "id": "yogurt-dip",
  "name": "Cucumber yogurt dip",
  "ingredients": [],
  "diet_tags": ["vegetarian"],
  "free_from": [],
  "prep_resources": ["bowl-yogurt"],
  "service_resources": ["spoon-yogurt"],
  "notes": ""
}
```

`free_from` is an organizer-supplied claim, never an automatically generated
result. Ingredient or resource conflicts cause findings.

### Resources

```json
{
  "id": "board-a",
  "name": "Preparation board A",
  "kind": "surface",
  "cleanable": true,
  "dedicated_to": null
}
```

Allowed `kind` values:

```text
surface, utensil, appliance, oil, service, other
```

Use `cleanable: false` for a resource that must be replaced or dedicated rather
than cleared by a cleaning boundary.

`dedicated_to` is a dish ID or `null`. A dedicated resource referenced by any
other dish is an error.

### Preparation

```json
{
  "order": 2,
  "dish": "tomato-rice",
  "clean_before": ["board-a"],
  "note": "Follow the documented sanitation procedure."
}
```

- Orders are positive and unique.
- A dish with preparation resources should have one step.
- `clean_before` must reference resources used by that dish.
- Declaring cleaning does not prove it was performed or adequate.

## `guests.csv`

Required header:

```csv
guest_id,name,avoid_allergens,required_diets,notes
```

Example:

```csv
guest_id,name,avoid_allergens,required_diets,notes
guest-1,Example guest,milk|sesame,vegan|gluten-free,Confirm on arrival
```

- Save as UTF-8.
- Multi-value cells use `|`.
- IDs use lowercase letters/digits plus `-` or `_`.
- Empty constraints are allowed.
- `notes` never changes status.
- Duplicate guest IDs are errors.

For privacy, `name` may be a pseudonym or seat/reference code.

## Identifier rules

Entity IDs:

```text
^[a-z][a-z0-9_-]{1,63}$
```

Allergen IDs:

```text
^[a-z][a-z0-9_]{1,63}$
```

Human spaces/case in entity IDs are normalized conservatively, but committed
source should already use stable IDs. Allergen naming aliases are limited to
direct category names; ingredient meanings are never inferred.

## Source revision workflow

1. Copy the prior case directory.
2. Change `revision`.
3. Update current package/recipe evidence.
4. Audit and resolve findings.
5. Build a new report and pack.
6. Keep the previous pack if change history matters.

The input digest makes accidental reuse of an old report visible.
