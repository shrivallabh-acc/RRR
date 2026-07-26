# Artifact Manifest — RRR Project
> The authoritative list of every project artifact, what state it tracks, and what must be updated
> when that state changes. Used by SOD (verify) and EOD (sync). If a file is not listed here, add it.

## How to use this file
**SOD step 1:** Skim each file's "Tracks" column and verify the claim matches reality.
**EOD step 5:** Walk the full file-by-file checklist in `.claude/commands/eod.md`. **Do not skip a
file because nothing changed there today** — stale content accumulates in untouched files, which is
exactly what caused the ADR-0014/0015 and LangGraph/Chroma drift. Every file with a status claim
must be verified on every EOD run.

---

## Root artifacts

| File | Tracks | Fields to check | Stale signal |
|------|--------|-----------------|--------------|
| `README.md` | Live project status, milestone table, ▶ Next action, daily log | `_last updated_` date; milestone row statuses; "▶ Next action" text; test count in status block | Date is yesterday's; test count differs from `pytest` output |
| `CLAUDE.md` | Project structure (what's built vs planned), test count, ADR/diagram counts, tech stack | "Built and tested ... (NNN tests)"; "Current status" paragraph; `tests/` directory listing | Test count; eval harness in "Remaining stubs" list after it's done |
| `pyproject.toml` | Dependencies — core vs optional | core deps list; `[dev]`, `[local-llm]`, `[rag]` groups | Heavy unused deps (chromadb, langgraph) in core when they should be optional |

---

## docs/

| File | Tracks | Fields to check | Stale signal |
|------|--------|-----------------|--------------|
| `docs/roadmap.md` | Milestone status (Design/M1–M7), work breakdown checkboxes, design-review action table | Milestone table rows; `[x]` vs `[ ]` checkboxes; design-review action "Status" column | Checkbox marked `[ ]` for work confirmed done; milestone table contradicts README |
| `docs/assessor_inputs.md` | Input contract reference for all 19 assessors — source taxonomy, JSON stubs, tier matrix | Assessor registry table (weights, sources, tier status); JSON stubs match actual `InputContract` models | Model field added but stub not updated; tier matrix contradicts `TierThresholds` config |
| `docs/data-collection-guide.md` | Operational collection guide — rrr-collect CLI reference, per-assessor steps, CI/CD integration | CLI flag reference; per-assessor step commands; freshness guidelines table | New assessor added but steps not documented; CLI flags changed but guide not updated |
| `docs/architecture.md` | Implementation status callout (first ~15 lines) | Test count; list of "built & tested" items; list of "not yet built" items | Test count behind reality; done items in "not yet built" |
| `docs/architecture-review.md` | Point-in-time audit findings + resolution status | Top Risks list; Maturity Ratings table; each Finding; Missing Artifacts table; Remediation plan | Finding listed as open when work is done; maturity scores not bumped after resolutions |
| `docs/ai-usage.md` | Every AI-assisted stage: design sessions, ADR decisions, implementation, testing, docs | Stage entries; each entry's "Influence" field | A session happened (design review, ADR acceptance, implementation) but no Stage entry exists |
| `docs/requirements.md` | FR/NFR list — stable; changes only if requirements change | FR/NFR text | Requirement marked as "planned" long after implementation |
| `docs/vision.md` | Goals, success metrics — stable | No status claims; verify no stale phase labels | "Phase 3" or other removed terminology |
| `docs/evaluation-plan.md` | Eval approach, golden dataset structure, acceptance thresholds | Status of eval harness and oracles | Says "not yet implemented" after eval is done |
| `docs/brain-schema.md` | Brain input contract — stable | No implementation status claims | Out-of-date field names vs actual `brain/*.json` |
| `docs/env-dep-schema.md` | Env/dep source schemas — stable | No implementation status claims | — |
| `docs/claude-code-prompt-devex.md` | Claude Code dev-ex guidance — stable reference | No status claims | — |

---

## adr/

| File | Tracks | Fields to check | Stale signal |
|------|--------|-----------------|--------------|
| `adr/0002-langgraph-for-orchestration.md` | Status: Accepted; impl deviation noted | "Implementation status (M3)" note | Note absent after LangGraph-vs-ThreadPoolExecutor decision was recorded |
| `adr/0008-evaluation-golden-dataset-llm-judge.md` | Status: Accepted | No impl note yet | Should get an impl note once `judge.py` lands |
| `adr/0013-verdict-veto-cap-gates.md` | Status: Accepted; gates realized via risk-factor severity | Implementation note if deviation exists | Deviation (severity-based not data-re-check) not recorded |
| `adr/0014-centralized-gate-engine.md` | Status: Accepted; impl deferred | "Implementation Note (2026-06-17)" block | Note missing or status still "Proposed" |
| `adr/0015-verdict-robustness-required-dimensions-confidence.md` | Status: Accepted; impl deferred | "Implementation Note (2026-06-17)" block | Note missing or status still "Proposed" |
| `adr/0016-assessment-model-v2-dimensions-and-tiers.md` | Status: Accepted (implemented 2026-07-09); all 16 items built; impl-notes for items 4–7 + items 8–16 | Status field; implementation notes | New item implemented but note not added |
| `adr/0017-make-ai-earn-its-place.md` | Status: Accepted 2026-06-30 (deviation: narrative-only) | Status field; deviation note | — |
| `adr/0023-data-collection-cli.md` | Status: Accepted 2026-07-09 — Phase 1 CLI ✅; Phase 2 Collect screen ✅ 2026-07-10; adapters ⬜ | Status field; Phase 1 + Phase 2 impl-notes present | Phase 2 adapters built without adding impl-note |
| All other ADRs (0001, 0003–0007, 0009–0012) | Status: Accepted; stable | Status field | Any ADR lacking a status line |

---

## diagrams/

| File | Tracks | Fields to check | Stale signal |
|------|--------|-----------------|--------------|
| `diagrams/README.md` | Diagram inventory (count + descriptions) | Count matches actual `.md` files in diagrams/ | Count says N but `ls diagrams/*.md` returns N±1 |
| `diagrams/01-system-architecture.md` | Implementation note: ThreadPoolExecutor vs LangGraph; Chroma not yet built | Impl note at top | Note absent; note says "not yet built" for something that is now built |
| `diagrams/03-assessment-sequence.md` | Implementation note: ThreadPoolExecutor; RAG not yet built | Impl note at top | Same as above |
| `diagrams/05-verdict-logic.md` | Gate logic — design matches as-built (severity → cap) | No explicit status note; gate logic correct | Gate logic contradicts ADR-0013 as-built deviation |
| `diagrams/06-memory-rag.md` | RAG design — planned, not yet built | Should note "planned, not yet implemented" | Note absent when Chroma is still unbuilt |
| `diagrams/08-evaluation.md` | Eval harness design | Should note impl status | Says "not yet built" after eval is done |
| Other diagrams (02, 04, 07, 09) | Design diagrams — stable unless architecture changes | No status claims | — |

---

## memory/ (auto-loaded each session)

| File | Tracks | Fields to check | Stale signal |
|------|--------|-----------------|--------------|
| `memory/project-state.md` | Current status, test count, ▶ NEXT ACTION, what's built, what's remaining | Status line date; test count; NEXT ACTION block; "Remaining" list | Date is old; NEXT ACTION not mirrored from README; done items still in "Remaining" |
| `memory/eod-readme-log.md` | EOD ritual convention + lessons | Artifact list in step 5 | A file added to the project but not in the step-5 list |
| `memory/sod-routine.md` | SOD ritual steps | Step 1 orient list | — |
| `memory/roadmap-open-questions.md` | Unresolved design questions | List of open questions | Resolved question not struck through |
| `memory/working-style.md` | Collaboration style preferences | — | — |
| `memory/rkt-brain-source.md` | Upstream data contract | — | — |

---

## Alignment script

`scripts/check_alignment.py` — the git-free drift detector. It asserts:
- No stale sentinel strings (e.g. "Phase 3", "No implementation yet") in any source
- Every `"<N> ADRs"` claim in docs matches the actual ADR file count
- Every `"<N> diagrams"` claim in docs matches the actual diagram file count
- The `output/__init__.py` stub sentinel produces a WARN (expected — M2 pending), not an error

Run after every EOD artifact sync to confirm green before closing.

---

## State variables (current ground truth — update here when they change)

> These are the single values every file above must agree on.
> If a number here differs from what a file says, that file is stale.

| Variable | Current value | Last verified |
|----------|---------------|---------------|
| Test count | **727** | 2026-07-10 (alignment script — hardening bundle 13 + Collect screen 6 new tests; 727 test functions) |
| ADR count | **23** (0001–0023) | 2026-07-10 (no new ADRs; impl-notes added to ADR-0020 + ADR-0023) |
| Diagram count | **9** (01–09) | 2026-06-26 |
| M1 status | ✅ Complete | 2026-06-15 |
| M2 status | ✅ Complete | `--dry-run` ✅ 2026-06-22 |
| M3 status | ✅ Complete | 2026-06-16 |
| M4 status | ✅ Complete | CLI ✅, SQLite+trends ✅, eval harness ✅, structural judge ✅ 2026-06-23, prose judge ✅ 2026-06-26 (FR-28), ADR-0014/0015 ✅, Chroma RAG ✅, LangGraph wrapper ✅, Docker ✅, BedrockProvider ✅ 2026-06-22, rrr-ingest ✅ 2026-06-22 |
| M5 status | ✅ Complete | ClaudeProvider ✅ 2026-06-25; ProseQualityJudge ✅ 2026-06-26; NiceGUI `rrr-ui` ✅ 2026-06-26; live APIs ✅ 2026-06-28; Trends tab ✅ 2026-06-28; TOC tagging ✅ 2026-06-28; programme filter (ADR-0022) ✅ 2026-06-29; Security gate-only dim (ADR-0016 item 2) ✅ 2026-06-29; UI redesign ✅ 2026-06-29; hosted persistence interface ✅ 2026-06-30; LangGraph architecture resolved ✅ 2026-06-30 |
| ADR-0014 | Accepted — implemented 2026-06-18 | 2026-06-25 |
| ADR-0015 | Accepted — implemented 2026-06-18 | 2026-06-25 |
| ADR-0016 | Fully implemented ✅ — all items 1–16 done. Items 8–16 (9 gate-only assessors) ✅ 2026-07-09 | 2026-07-09 |
| ADR-0017 | Accepted — implemented 2026-06-30 (deviation: narrative-only; no classification adjudication; `ProseQualityJudge` eval gate) | 2026-06-30 |
| ADR-0018 | Accepted — implemented 2026-06-22 | 2026-06-29 |
| ADR-0019 | Accepted — implemented 2026-06-22 | 2026-06-29 |
| ADR-0020 | Accepted — impl-note 2026-07-10 (M7 Phase 2 Collect screen) | 2026-07-10 |
| ADR-0021 | Accepted — implemented 2026-06-28 | 2026-06-29 |
| ADR-0022 | Accepted — implemented 2026-06-29 | 2026-06-29 |
| ▶ Next action | M7 Phase 2 Collect screen ✅ + T-02/T-03/T-04/T-07 ✅ 2026-07-10 (727 tests). Next: M7 Phase 2 remaining — tool adapters (snyk, sonarqube, k6, axe, grafana, datadog) or `docs/data-collection-guide.md`. | 2026-07-10 EOD |
