# g4_missing_data — intentionally no brain file

This sample exercises **graceful degradation → INCOMPLETE** (ADR-0005, FR-8). There is **no
`brain/` directory** here on purpose: the upstream RKT export is unavailable, so the three
brain-fed dimensions (Scope, Estimation, Test Readiness) cannot be assessed. Only Environment and
Dependency have usable data — **2 successful dimensions < `minimum_assessors` (3)** → the verdict
must be **INCOMPLETE**, not a low GO/NO-GO score.
