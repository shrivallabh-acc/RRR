"""One-shot script: run pipeline.assess() on g2–g5 and print JSON per fixture."""
from __future__ import annotations
import json
from pathlib import Path
import sys

# Make sure the src layout is importable when run as a script.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rrr.config import ConfigLoader
from rrr.pipeline import assess

GOLDEN = ROOT / "tests" / "golden"
VS = "Retirement-Services"

FIXTURES = [
    ("g2_failing_tests",  "Launch 37 - Payments Hub"),
    ("g3_borderline",     "Launch 38 - Advice Workbench"),
    ("g4_missing_data",   "Launch 39 - Missing Data"),   # no brain dir — INCOMPLETE expected
    ("g5_scope_creep",    "Launch 40 - Onboarding Plus"),
]


def _overrides(sample: str) -> dict:
    inp = GOLDEN / sample / "inputs"
    brain_dir = inp / "brain"
    return {
        "sources": {
            "brain": {"dir": str(brain_dir), "value_stream": VS},
            "environment": {"type": "file", "path": str(inp / "environment.json")},
            "dependency":  {"type": "file", "path": str(inp / "dependency.json")},
        }
    }


for sample, release in FIXTURES:
    print(f"\n{'='*60}")
    print(f"FIXTURE: {sample}  |  RELEASE: {release}")
    print("=" * 60)
    try:
        out = assess(ConfigLoader.load(overrides=_overrides(sample)), release=release)
        print(json.dumps(out.model_dump(mode="json"), indent=2))
    except Exception as exc:
        print(f"ERROR: {exc}")
