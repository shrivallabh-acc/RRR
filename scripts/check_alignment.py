#!/usr/bin/env python
"""Artifact alignment check — verifies the docs agree with reality (EOD ritual / on demand).

Static and stdlib-only (fast, no deps). Complements the test gate (`/check`): this answers
"do all project artifacts still agree with each other and the code?" rather than "do tests pass?".

Checks (FAIL = drift, exit 1):
  1. No stale markers in the project docs (e.g. "No implementation yet", "Phase 3").
  2. Any "<N> ADRs" / "<N> diagrams" claim in the docs matches the real file counts.
  3. ADR status-header contradictions: a Status line that still says "deferred" when the
     same file already has an implementation note saying the work is built.
  4. Diagram implementation notes: any diagram that says "not yet built" for a feature that
     is now known to be complete (LangGraph, Chroma RAG).
WARN (does not fail): leftover stub sentinels in `src/`.

Run:  .venv/Scripts/python.exe scripts/check_alignment.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Strings that must never appear in the project docs once implementation is underway.
# (RRR uses "Phase" only for local→external, so "Phase 3" is always stale.)
FORBIDDEN_MARKERS = (
    "No implementation yet",
    "no business logic",
    "scaffolding stub",
    "Phase 3",
    "Phase-3",
)

# Features that are built — these phrases must not appear as "not yet built" claims
# in diagram implementation notes or similar live-status blocks.
BUILT_FEATURES = (
    "LangGraph",
    "Chroma",
)

# Phrases that contradict a "Built" implementation note in an ADR file.
# If an ADR Status header contains one of these AND the file also has a "Built" impl note,
# the status header is stale.
ADR_DEFERRED_PHRASES = (
    "implementation deferred",
    "impl deferred",
    "deferred to M",
)


def project_docs() -> list[Path]:
    """The artifact docs whose claims must stay aligned (excludes .claude/ command defs,
    the .venv, and non-project root notes)."""
    docs = [ROOT / "README.md", ROOT / "CLAUDE.md"]
    for sub in ("docs", "diagrams", "adr"):
        docs += sorted((ROOT / sub).glob("*.md"))
    return [d for d in docs if d.exists()]


def live_text(doc: Path) -> str:
    """Doc content subject to alignment checks. The README's 'Daily Progress Log' is an
    append-only historical changelog — past entries are point-in-time and legitimately
    mention old states/counts — so it is excluded (live status sits above it).
    Similarly, ai-usage.md Stage entries are historical records; only the header/summary
    lines at the top of each stage are live."""
    text = doc.read_text(encoding="utf-8")
    if doc.name == "README.md":
        idx = text.find("## Daily Progress Log")
        if idx != -1:
            text = text[:idx]
    if doc.name == "ai-usage.md":
        # Stage entries are point-in-time records; the header/intro is the live section.
        idx = text.find("## Stage 0")
        if idx != -1:
            text = text[:idx]
    return text


def check_adr_status_contradictions(problems: list[str]) -> None:
    """Fail if any ADR status header says 'deferred' but the file has a Built impl note.

    An ADR that has been implemented must have a Status header reflecting that. Leaving
    'implementation deferred' in the Status line after adding a 'Built' note is the exact
    pattern that caused stale status drift (ADR-0014, ADR-0015).
    """
    for adr_file in sorted((ROOT / "adr").glob("0*.md")):
        text = adr_file.read_text(encoding="utf-8")
        # Check if there is a "Built" or "built" implementation note
        has_built_note = bool(re.search(r"(?i)implementation note.*built", text, re.DOTALL))
        if not has_built_note:
            # Also check for the pattern "## Implementation Note (YYYY-MM-DD)\nBuilt"
            has_built_note = bool(re.search(r"## Implementation Note.*?\nBuilt", text, re.DOTALL))
        if has_built_note:
            # Status line should not say any deferred phrase
            status_match = re.search(r"^\s*[-*]\s*\*\*Status:\*\*.*|^- \*\*Status:\*\*.*|Status:.*",
                                     text, re.M)
            if status_match:
                status_line = status_match.group()
                for phrase in ADR_DEFERRED_PHRASES:
                    if phrase.lower() in status_line.lower():
                        problems.append(
                            f"adr/{adr_file.name}: Status header says '{phrase}' but file "
                            f"has a Built implementation note — update the status header"
                        )
                        break


def check_diagram_impl_notes(problems: list[str]) -> None:
    """Fail if any diagram's implementation note claims a built feature is 'not yet built'.

    Matches within a single line only — a feature name appearing far above a 'not yet built'
    clause that refers to something else (e.g. '--dry-run') must not trigger a false positive.
    """
    for diag in sorted((ROOT / "diagrams").glob("*.md")):
        if diag.name == "README.md":
            continue
        text = diag.read_text(encoding="utf-8")
        for feature in BUILT_FEATURES:
            # Single-line search only: the feature and the stale phrase must appear on the
            # same line to avoid false positives where 'not yet built' refers to something
            # else entirely (e.g. '--dry-run') several lines after the feature is mentioned.
            if re.search(
                rf"{re.escape(feature)}.*not yet built|not yet built.*{re.escape(feature)}",
                text, re.IGNORECASE
            ):
                rel = diag.relative_to(ROOT)
                problems.append(
                    f"{rel}: claims '{feature}' is 'not yet built' but it is implemented"
                )


def main() -> int:
    """Run all alignment checks and report drift."""
    adr_count = len([p for p in (ROOT / "adr").glob("*.md") if p.name != "CLAUDE.md"])
    diagram_count = len([p for p in (ROOT / "diagrams").glob("*.md") if p.name != "README.md"])
    src_modules = sorted((ROOT / "src" / "rrr").rglob("*.py"))
    test_fns = sum(
        len(re.findall(r"^def (test_\w+)", p.read_text(encoding="utf-8"), re.M))
        for p in (ROOT / "tests").rglob("test_*.py")
    )

    problems: list[str] = []
    warnings: list[str] = []

    for doc in project_docs():
        text = live_text(doc)
        rel = doc.relative_to(ROOT)
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                problems.append(f"stale marker {marker!r} in {rel}")
        for m in re.finditer(r"(\d+)\s+ADRs\b", text):
            if int(m.group(1)) != adr_count:
                problems.append(f"{rel} claims {m.group(1)} ADRs; actual is {adr_count}")
        for m in re.finditer(r"(\d+)\s+diagrams\b", text):
            if int(m.group(1)) != diagram_count:
                problems.append(f"{rel} claims {m.group(1)} diagrams; actual is {diagram_count}")

    # ADR-specific checks — status headers must not contradict implementation notes
    check_adr_status_contradictions(problems)

    # Diagram-specific checks — impl notes must not claim built features are unbuilt
    check_diagram_impl_notes(problems)

    for mod in src_modules:
        if "Stub — see" in mod.read_text(encoding="utf-8"):
            warnings.append(f"stub sentinel still present in {mod.relative_to(ROOT)}")

    print(
        f"counts: {adr_count} ADRs · {diagram_count} diagrams · "
        f"{len(src_modules)} src modules · {test_fns} test functions"
    )
    for w in warnings:
        print(f"  WARN: {w}")
    for p in problems:
        print(f"  FAIL: {p}")

    if problems:
        print(f"ALIGNMENT: FAIL — {len(problems)} drift issue(s)")
        return 1
    print("ALIGNMENT: PASS — docs agree with reality")
    return 0


if __name__ == "__main__":
    sys.exit(main())
