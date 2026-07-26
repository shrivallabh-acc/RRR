"""Unit tests for GateEngine (ADR-0014)."""

from __future__ import annotations

from rrr.config import ConfigLoader
from rrr.models.enums import RiskSeverity, Verdict
from rrr.models.evidence import RiskFactor
from rrr.orchestration.gate_engine import GateEngine

CFG = ConfigLoader.load()
GATES = CFG.gates


def _risk(
    description: str,
    severity: RiskSeverity,
    *,
    gate: str | None = None,
) -> RiskFactor:
    return RiskFactor(description=description, severity=severity, gate=gate)


# --- named gate path (ADR-0014) -----------------------------------------------------------


def test_named_gate_environment_down_maps_to_config_verdict() -> None:
    risk = _risk("api-gateway is down", RiskSeverity.CRITICAL, gate="environment_down")
    caps = GateEngine.apply([risk], GATES)
    assert len(caps) == 1
    cap, reason = caps[0]
    assert cap is GATES.environment_down  # respects what config says (NO_GO)
    assert "api-gateway is down" in reason


def test_named_gate_environment_degraded_maps_to_config_verdict() -> None:
    risk = _risk("database is degraded", RiskSeverity.MAJOR, gate="environment_degraded")
    caps = GateEngine.apply([risk], GATES)
    assert len(caps) == 1
    assert caps[0][0] is GATES.environment_degraded  # CONDITIONAL


def test_named_gate_dependency_failed_maps_to_config_verdict() -> None:
    risk = _risk("payments integration failed", RiskSeverity.CRITICAL, gate="dependency_failed")
    caps = GateEngine.apply([risk], GATES)
    assert caps[0][0] is GATES.dependency_failed  # NO_GO


def test_named_gate_dependency_blocking_maps_to_config_verdict() -> None:
    risk = _risk("auth-service not started", RiskSeverity.MAJOR, gate="dependency_blocking")
    caps = GateEngine.apply([risk], GATES)
    assert caps[0][0] is GATES.dependency_blocking  # CONDITIONAL


def test_named_gate_blocker_defects_maps_to_config_verdict() -> None:
    risk = _risk("2 open blocker defect(s)", RiskSeverity.CRITICAL, gate="blocker_defects")
    caps = GateEngine.apply([risk], GATES)
    assert caps[0][0] is GATES.blocker_defects  # NO_GO


# --- unknown / non-Verdict named gate falls back to severity ----------------------------


def test_unknown_gate_name_falls_back_to_severity() -> None:
    # "scope_creep_threshold" is a float field — not a Verdict — so severity fallback kicks in.
    risk = _risk("scope grew 30%", RiskSeverity.MAJOR, gate="scope_creep_threshold")
    caps = GateEngine.apply([risk], GATES)
    assert len(caps) == 1
    assert caps[0][0] is Verdict.CONDITIONAL  # severity MAJOR → CONDITIONAL


def test_completely_unknown_gate_name_falls_back_to_severity() -> None:
    risk = _risk("some risk", RiskSeverity.CRITICAL, gate="nonexistent_gate")
    caps = GateEngine.apply([risk], GATES)
    assert caps[0][0] is Verdict.NO_GO  # CRITICAL fallback


# --- no gate name → pure severity fallback -----------------------------------------------


def test_no_gate_name_critical_severity_maps_to_no_go() -> None:
    risk = _risk("E2E pass rate below floor", RiskSeverity.CRITICAL)
    caps = GateEngine.apply([risk], GATES)
    assert caps[0][0] is Verdict.NO_GO


def test_no_gate_name_major_severity_maps_to_conditional() -> None:
    risk = _risk("scope grew 15%", RiskSeverity.MAJOR)
    caps = GateEngine.apply([risk], GATES)
    assert caps[0][0] is Verdict.CONDITIONAL


def test_no_gate_name_minor_severity_produces_no_cap() -> None:
    risk = _risk("minor quality issue", RiskSeverity.MINOR)
    caps = GateEngine.apply([risk], GATES)
    assert caps == []


# --- gates.enabled=False disables all caps -----------------------------------------------


def test_gates_disabled_returns_empty() -> None:
    disabled = GATES.model_copy(update={"enabled": False})
    risk = _risk("critical thing", RiskSeverity.CRITICAL)
    assert GateEngine.apply([risk], disabled) == []


# --- multiple risk factors ---------------------------------------------------------------


def test_multiple_risk_factors_returns_all_caps() -> None:
    risks = [
        _risk("dep failed", RiskSeverity.CRITICAL, gate="dependency_failed"),
        _risk("scope grew", RiskSeverity.MAJOR),
        _risk("minor quality issue", RiskSeverity.MINOR),
    ]
    caps = GateEngine.apply(risks, GATES)
    assert len(caps) == 2  # MINOR produces no cap
    verdicts = {cap for cap, _ in caps}
    assert Verdict.NO_GO in verdicts
    assert Verdict.CONDITIONAL in verdicts
