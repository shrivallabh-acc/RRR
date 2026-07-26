---
description: Post-decision artifact map — given a decision just made, identify every doc, ADR, code file, test, and memory entry that must change
---

Map the full artifact impact of a decision so documentation drift is caught at the moment of choice,
not discovered at EOD. Run this whenever a significant design or implementation decision is made —
during SOD path selection, mid-session pivots, or any time you say "we'll do X instead of Y".

**Decision to map:** $ARGUMENTS

---

## How to run

1. **Parse the decision** — identify: what was decided, what was deferred/rejected, and what constraint
   or evidence drove the choice.

2. **Classify the decision type** — each type has a predictable artifact footprint:

   | Decision type | Likely artifact changes |
   |---------------|------------------------|
   | New feature / capability | code files, new tests, roadmap ✅, ai-usage log entry |
   | Design change (algorithm, schema, boundary) | ADR (new or impl-note), architecture.md, affected tests |
   | Deferral / scope cut | roadmap note, CLAUDE.md status, project-state memory |
   | Dependency change (new/removed package) | pyproject.toml, CLAUDE.md stack, potentially ADR |
   | Provider / LLM behavior change | ADR (ADR-0006/0009/0017 territory), ai-usage log |
   | Gate / scoring rule change | ADR (ADR-0013/0014/0015 territory), scoring tests, property tests |
   | Naming / refactor | all files using the old name — run a grep first |

3. **Produce the impact checklist** — for EACH affected artifact:

   ```
   ### Code
   - [ ] src/rrr/<module>/<file>.py — [create / modify: what changes and why]
   
   ### ADRs
   - [ ] adr/NNNN.md — [create: title + status=Proposed] OR [update: add impl-note or deviation]
   
   ### Documentation
   - [ ] docs/roadmap.md — [item name: flip status / add note]
   - [ ] docs/architecture.md — [section: what updates]
   - [ ] docs/ai-usage.md — [Stage N: log this decision with prompt and influence]
   - [ ] CLAUDE.md — [status block / stack / structure: what updates]
   
   ### Tests
   - [ ] tests/unit/test_<file>.py — [create / update: what new cases are needed]
   - [ ] tests/property/test_scoring_properties.py — [update invariants if scoring changed]
   - [ ] tests/golden/g<N>/ideal.json — [update oracle if verdict/score expectation changes]
   
   ### Memory
   - [ ] project-state memory — [▶ Next action pointer / STATUS / key durable facts]
   - [ ] roadmap-open-questions memory — [resolve or add question]
   ```

4. **Flag conflicts** — if the decision contradicts an existing ADR, a hard constraint (local-first,
   deterministic score), or a roadmap dependency, surface the conflict explicitly before proceeding.

5. **Handoff** — the checklist output from this command feeds directly into `/eod` step 5.
   Any ✅ items completed immediately can be noted; the rest carry forward.

---

Run offline. No external calls. If the decision involves a new external dependency or network
endpoint, flag it as a potential ADR-0010 violation before the checklist.
