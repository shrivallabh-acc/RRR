# ADR 0003: SQLite for Persistence

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
Every assessment must be persisted so readiness can be compared over time (trends:
improving / degrading / stable). RRR ships as a portable CLI that should run anywhere
with no infrastructure setup.

## Decision
Use **SQLite** (file-based, zero-config) as the persistence store. DB path and
retention are configurable (`memory.db_path`, `retention_days: 90`); persistence uses
a retry policy (3 attempts, 5s interval).

## Consequences
- No server to provision; the database is a single file, easy to back up and ship.
- Sufficient for single-user CLI workloads and historical trend queries.
- Not suited to high-concurrency multi-writer scenarios — acceptable for this design.
