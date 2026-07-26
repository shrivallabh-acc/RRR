"""Deterministic evaluation metrics for the RRR golden dataset.

Implements: verdict accuracy, macro-F1, score MAE, dimension-score MAE,
and risk-factor precision/recall/F1.  No LLM involvement — pure math.
See docs/evaluation-plan.md §3 for the metric definitions.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rrr.models.enums import Verdict

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden"
ALL_VERDICTS = [Verdict.GO, Verdict.NO_GO, Verdict.CONDITIONAL, Verdict.INCOMPLETE]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FixtureResult:
    sample: str
    predicted_verdict: Verdict
    ideal_verdict: Verdict
    predicted_score: int | None
    ideal_score: int | None
    dimension_maes: dict[str, float]  # dim → |predicted - expected|
    risk_f1: float
    risk_precision: float
    risk_recall: float


@dataclass
class EvalReport:
    fixtures: list[FixtureResult] = field(default_factory=list)

    @property
    def verdict_accuracy(self) -> float:
        if not self.fixtures:
            return 0.0
        correct = sum(1 for f in self.fixtures if f.predicted_verdict == f.ideal_verdict)
        return correct / len(self.fixtures)

    @property
    def macro_f1(self) -> float:
        """Macro-averaged F1 over all verdict labels present in the ideal set."""
        f1s = []
        for label in ALL_VERDICTS:
            tp = sum(
                1
                for f in self.fixtures
                if f.ideal_verdict == label and f.predicted_verdict == label
            )
            fp = sum(
                1
                for f in self.fixtures
                if f.ideal_verdict != label and f.predicted_verdict == label
            )
            fn = sum(
                1
                for f in self.fixtures
                if f.ideal_verdict == label and f.predicted_verdict != label
            )
            if tp + fp == 0 and tp + fn == 0:
                continue  # label absent from both predicted and ideal — skip
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0)
        return sum(f1s) / len(f1s) if f1s else 0.0

    @property
    def mean_score_mae(self) -> float:
        pairs = [
            (f.predicted_score, f.ideal_score)
            for f in self.fixtures
            if f.predicted_score is not None and f.ideal_score is not None
        ]
        if not pairs:
            return 0.0
        return sum(abs(p - i) for p, i in pairs) / len(pairs)

    @property
    def mean_risk_f1(self) -> float:
        if not self.fixtures:
            return 0.0
        return sum(f.risk_f1 for f in self.fixtures) / len(self.fixtures)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_ideal(sample: str) -> dict:
    path = GOLDEN / sample / "ideal.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _risk_f1(predicted: Sequence[str], expected: Sequence[str]) -> tuple[float, float, float]:
    """Simple token-overlap F1: a predicted factor matches if any expected factor is a substring."""
    if not expected and not predicted:
        return 1.0, 1.0, 1.0
    if not expected:
        return 0.0, 1.0, 0.0  # precision=0 (no expected), recall vacuously 1
    if not predicted:
        return 0.0, 0.0, 0.0

    def _matches(pred: str, exp_list: Sequence[str]) -> bool:
        p = pred.lower()
        return any(e.lower() in p or p in e.lower() for e in exp_list)

    tp_pred = sum(1 for p in predicted if _matches(p, expected))
    tp_exp = sum(1 for e in expected if _matches(e, predicted))

    precision = tp_pred / len(predicted)
    recall = tp_exp / len(expected)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return f1, precision, recall


def _dim_maes(predicted_dims: list[dict], ideal: dict) -> dict[str, float]:
    ideal_scores: dict = ideal.get("dimension_scores", {})
    maes: dict[str, float] = {}
    pred_map = {d["dimension"]: d["score"] for d in predicted_dims if d.get("available")}
    for dim, spec in ideal_scores.items():
        if dim in pred_map:
            maes[dim] = abs(pred_map[dim] - spec["expected"])
    return maes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_fixture(
    sample: str,
    predicted_verdict: Verdict,
    predicted_score: int | None,
    predicted_dims: list[dict],
    predicted_risk_factors: list[str],
) -> FixtureResult:
    ideal = _load_ideal(sample)
    ideal_verdict = Verdict(ideal["verdict"])
    ideal_score: int | None = ideal.get("score")

    f1, prec, rec = _risk_f1(predicted_risk_factors, ideal.get("expected_risk_factors", []))

    return FixtureResult(
        sample=sample,
        predicted_verdict=predicted_verdict,
        ideal_verdict=ideal_verdict,
        predicted_score=predicted_score,
        ideal_score=ideal_score,
        dimension_maes=_dim_maes(predicted_dims, ideal),
        risk_f1=f1,
        risk_precision=prec,
        risk_recall=rec,
    )
