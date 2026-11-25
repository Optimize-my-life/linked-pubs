# Application domain: human nutrition, facts feed optimisation

Status: accepted
Date: 2026-11-25

## Context
PhD focus: personal habit and decision optimisation on large-scale datasets, with
solvability as a core metric. The tool needs an application field.

## Decision
Human nutrition. Extracted statements are inputs to optimisation models (bounds,
coefficients, conditions), not only text to read. Statements are therefore typed and
numeric where possible (see `architecture.md`, statement types). Resolution must
handle units, populations and source authority, so that merged facts give a
consistent (solvable) constraint set.

## Why
Nutrition has authoritative quantitative sources (DRIs, EFSA DRVs, D-A-CH) that are
both PDFs and published tables, which gives a gold standard for extraction, and
large person-level datasets (NHANES, FoodData Central) for evaluation at scale.

## Alternatives
General biomedical claims only: more benchmarks (SciFact, HealthVer), but no link to
optimisation. Kept as a benchmark, not as the application.
