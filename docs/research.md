# Research and differentiation record

Research date: **2026-07-30**
Scope: public GitHub repositories, adjacent open-source products, community
problem reports, and current primary regulatory/public-health sources.

This is a dated search record, not proof that no comparable work can exist.
Repository names, search indexes, and products change. Re-run the queries before
making a future novelty claim.

## Local and prior-work exclusion

Before choosing a concept, the workspace inventory and prior project record were
reviewed. Existing work already covered developer onboarding, repository
analysis, release tooling, test quality, data privacy, local data workbenches,
game-development labs, manuals-to-maintenance plans, laundry constraints,
hardware compatibility, greenhouse/energy telemetry, and several evidence or
archive tools.

Concepts in those families were rejected. AllergenGrid targets a different
primary user and workflow: event organizers and small kitchens reconciling
guest constraints, explicit ingredient declarations, and physical resource
reuse.

## GitHub repository queries

Queries were sent to GitHub's public repository search API, sorted by stars.

| Query | Public repository results | Assessment |
| --- | ---: | --- |
| `allergen matrix catering` | 0 | No result |
| `"dietary matrix" event` | 0 | No result |
| `"cross-contact" allergen menu` | 0 | No result |
| `"guest dietary" menu` | 1 | Unrelated LlamaIndex/MCP multi-agent catering exercise |
| `"food allergy" event planner` | 0 | No result |
| `AllergenGrid in:name` | 0 | Name clear in search |
| `AllergyGrid in:name` | 0 | Adjacent name clear in search |
| `MenuMatrix allergen in:name,description` | 0 | No result |

Web search did find adjacent products:

- [OpenRSVP](https://www.openrsvp.app/) records RSVP dietary requirements but
  does not model dish declarations or physical cross-contact paths.
- [Norish](https://norish.dev/) is a broad recipe/grocery planner with optional
  AI allergy insight, not an event-specific declaration auditor.
- [Open Food Facts](https://github.com/openfoodfacts/openfoodfacts-server) is a
  product database, not a guest/menu/resource planner.
- Commercial allergen grids exist, which validates the operational need, but
  the search did not surface an open-source offline tool with this combination.

The uncovered combination was:

1. explicit guest constraints;
2. explicit `contains` / `may_contain` / verification evidence;
3. preparation order and cleaning boundaries;
4. service-utensil cross-contact;
5. uncertainty-first action states;
6. print and machine outputs from the same analysis;
7. deterministic, independently verifiable offline package.

## Need evidence

The [US FDA](https://www.fda.gov/consumers/consumer-updates/have-food-allergies-read-label)
defines nine major food allergens and distinguishes mandatory `Contains`
declarations from voluntary `may contain` statements. It also advises checking
the complete ingredient list and re-checking labels because ingredients can
change.

The [European Commission](https://food.ec.europa.eu/food-safety/campaign-2026/allergies_en)
lists 14 allergens that must be declared and notes that allergen information for
non-prepacked foods must be available.

The [US CDC](https://www.cdc.gov/restaurant-food-safety/php/practices/food-allergy-reactions.html)
reports operational gaps in restaurants and highlights ingredient lists,
separate equipment/areas when feasible, thorough cleaning and sanitizing, and a
plan for serving customers with food allergies.

A community request about an allergy-friendly birthday-party page appeared in
[r/webdev](https://www.reddit.com/r/webdev/comments/1girood/creating_a_simple_food_allergyfriendly_website/).
It is anecdotal rather than authoritative, but it supports the event-organizer
use case.

## Star and discovery hypothesis

Stars cannot be promised. The release is structured to improve the odds of
organic discovery:

- searchable problem/domain name;
- useful outside software engineering;
- zero runtime dependencies and no hosted service;
- a committed passing demo and an intentionally failing demo;
- a visual HTML/print artifact plus JSON and exit codes;
- clear privacy and safety posture;
- deterministic release files and one-file execution;
- bilingual entry documentation.

Success should be measured by real usage, issues, and retained contributors—not
by a fabricated star forecast.

## Revalidation checklist

Before a later major release:

1. repeat the exact GitHub queries;
2. search GitHub topics for `food-allergy`, `allergen`, `catering`, and
   `event-planning`;
3. review new adjacent tools and document meaningful overlap;
4. confirm current FDA/EU allergen lists and applicable local rules;
5. revise novelty wording if a comparable repository now exists.
