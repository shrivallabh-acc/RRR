# ADRs — layer orientation

Current count: **23 ADRs** (ADR-0001 through ADR-0023).
`scripts/check_alignment.py` asserts this count — update the status line in `CLAUDE.md` when adding one.

## Lifecycle rules
Full rules (when to create, when to add an impl-note, format, numbering) are in
`.claude/rules/adr-lifecycle.md` — loaded automatically when you open files in this directory.

## Quick-reference format
```
# ADR-NNNN: Title
Status: Proposed | Accepted | Deprecated | Superseded by ADR-XXXX
Context:      why this decision needed to be made
Decision:     what was decided
Consequences: what this enables and what it forecloses
[Implementation note: YYYY-MM-DD — added after build; never rewrite the original decision]
```

## Proposed ADRs — decision documented, implementation pending
_(none currently — all accepted)_

## Recently accepted
- ADR-0017 — Make AI earn its place — Status: Accepted 2026-06-30 (deviation noted: narrative-only, not classification adjudication)
- ADR-0016 — Assessment model v2 (dimensions and tiers) — Status: Accepted 2026-07-09 (all 16 items implemented; impl-notes for items 3–16 in file)
- ADR-0023 — Data collection CLI (`rrr-collect` + `rrr-ui` Collect screen) — Status: Accepted 2026-07-09 (Phase 1 CLI ✅; Phase 2 Collect screen ✅ 2026-07-10; tool adapters remain)
