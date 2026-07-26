# ADR 0004: Pydantic v2 for Data Models & Validation

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
RRR ingests data from multiple sources (`brain/*.json`, CSV/JSON files, live APIs,
YAML config) and emits a versioned output schema. Inputs may be malformed, and
conclusions must be trustworthy. We need strong validation at every boundary.

## Decision
Use **Pydantic v2** for all data models — `DimensionResult`, `ToolInvocationModel`,
`EvidenceRecordModel`, `AssessmentOutputModel`, and config models. Use `Field`
validators and `model_validator`s (e.g. weights must sum to 1.0). All public functions
carry type hints.

## Consequences
- Validation failures surface early with clear errors (e.g. `ConfigurationError`).
- The output model is versioned (`schema_version "1.0.0"`) for forward compatibility.
- Couples the project to Pydantic v2 semantics (distinct from v1).
