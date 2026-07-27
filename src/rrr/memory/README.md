# Memory

Persistence and vector memory for RRR assessments. All storage is **local-first** —
no cloud backends in Phase 1 (ADR-0010).

---

## Module overview

| File | Purpose |
|---|---|
| `store.py` | `AbstractAssessmentStore` ABC + `SQLiteAssessmentStore` implementation |
| `__init__.py` | Public re-exports: `AbstractAssessmentStore`, `AssessmentStore`, `SQLiteAssessmentStore` |

`AssessmentStore` is an alias for `SQLiteAssessmentStore` — the canonical implementation.

---

## SQLiteAssessmentStore

Persists `AssessmentOutputModel` records to a local SQLite database.

**Features:**
- **WAL mode** (`PRAGMA journal_mode=WAL`) on every open — allows concurrent readers
  while a write is in progress.
- **Schema migration guard** — `PRAGMA user_version` stamped at schema version on
  first open; subsequent opens check and migrate incrementally.
- **Parent directory creation** — if `sqlite_path` parent directories don't exist,
  they're created automatically.
- **Chroma RAG** (optional) — if `chroma_path` is set, each saved assessment is
  embedded as a 6-dimensional vector `[scope, estimation, environment,
  test_readiness, dependency, score/100]`. `similar_to()` returns the most
  similar historical assessments for RAG-enriched rationale generation.

---

## Key methods

```python
store = AssessmentStore("data/local/rrr.sqlite")

# Persist a completed assessment
store.save(assessment_output_model)

# Retrieve the most recent assessment for a release
prior = store.latest_for(release="RetirePlus RC", value_stream="OSM")

# Full history for a release (newest first)
history = store.history(release="RetirePlus RC", value_stream="OSM", limit=10)

# All recent assessments (for the dashboard history panel)
records = store.all_recent(value_stream="OSM", limit=50)

# All distinct assessed release names (for the trends panel)
releases = store.assessed_releases(value_stream="OSM")

# Vector similarity search (requires chroma_path configured)
similar = store.similar_to(assessment_output_model, k=3)

store.close()
```

---

## Extending the store

To add a new persistence backend, subclass `AbstractAssessmentStore` and implement
all abstract methods. The `build_store()` factory in `pipeline.py` selects the backend
based on `config.memory.backend`.

Currently only `"sqlite"` is supported. The abstract interface (`AbstractAssessmentStore`)
keeps orchestration code decoupled from the storage mechanism.

---

## Configuration

```yaml
memory:
  sqlite_path: "./data/local/rrr.sqlite"   # where the SQLite file lives
  chroma_path: null                          # set a directory path to enable Chroma RAG
  rag_top_k: 3                              # number of similar assessments to retrieve
```

Enable Chroma RAG (requires `pip install "rrr[rag]"`):

```yaml
memory:
  sqlite_path: "./data/local/rrr.sqlite"
  chroma_path: "./data/local/chroma"
  rag_top_k: 3
```
