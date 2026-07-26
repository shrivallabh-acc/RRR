# ADR 0005: Graceful Degradation via Weight Redistribution

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
Assessor agents depend on external inputs (brain snapshots, files, live APIs) that may
be missing, slow, or invalid. A release verdict should remain useful even when one or
two dimensions cannot be assessed — a single failure must not abort the whole run.

## Decision
When a dimension is unavailable, **redistribute its weight equally among the available
dimensions** and continue. Confidence is capped (any tool fail → 0.5; all fail → 0.0 +
INCOMPLETE). A verdict is produced as long as at least `minimum_assessors` (default 3)
dimensions succeed; otherwise the verdict is **INCOMPLETE**.

## Consequences
- No total failure: partial inputs still yield an actionable verdict.
- Scoring remains normalized regardless of how many dimensions participated.
- Verdicts carry confidence + audit trail so degraded runs are transparent to the user.
