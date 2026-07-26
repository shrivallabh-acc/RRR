"""Persistence & RAG memory — local-first SQLite with optional Chroma index (FR-14, ADR-0003/0007).

``AbstractAssessmentStore`` defines the persistence contract; ``SQLiteAssessmentStore``
(aliased as ``AssessmentStore``) is the canonical impl. Future backends implement the
abstract class without touching orchestration code.
"""

from __future__ import annotations

from rrr.memory.store import (
    AbstractAssessmentStore,
    AssessmentStore,
    SQLiteAssessmentStore,
)

__all__ = [
    "AbstractAssessmentStore",
    "AssessmentStore",
    "SQLiteAssessmentStore",
]
