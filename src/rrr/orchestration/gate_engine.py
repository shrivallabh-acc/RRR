"""Centralized, config-driven gate engine (ADR-0014).

Each assessor emits a named ``gate`` signal on its ``RiskFactor`` instances.
``GateEngine.apply`` looks the name up in ``GatesConfig`` to determine the
verdict cap — making the ``gates:`` config block genuinely load-bearing.

Risk factors without a named gate (``gate=None``) fall back to severity-based
capping (CRITICAL→NO_GO, MAJOR→CONDITIONAL) so pre-ADR-0014 assessors continue
to work without modification.
"""

from __future__ import annotations

from rrr.config.schema import GatesConfig
from rrr.models.enums import RiskSeverity, Verdict
from rrr.models.evidence import RiskFactor

_SEVERITY_CAP: dict[RiskSeverity, Verdict] = {
    RiskSeverity.CRITICAL: Verdict.NO_GO,
    RiskSeverity.MAJOR: Verdict.CONDITIONAL,
}


class GateEngine:
    """Maps risk factors to verdict caps using named config gates or severity fallback."""

    @staticmethod
    def apply(
        risk_factors: list[RiskFactor],
        gate_config: GatesConfig,
    ) -> list[tuple[Verdict, str]]:
        """Return ``(cap, reason)`` for each gate-triggering risk factor.

        Named gate path (preferred, ADR-0014): if ``risk.gate`` is set, look up
        the corresponding field in ``gate_config``.  If that field is a ``Verdict``
        instance, use it as the cap.  If the lookup fails (unknown name or non-Verdict
        field), fall through to the severity fallback.

        Severity fallback: CRITICAL→NO_GO, MAJOR→CONDITIONAL, MINOR→no cap.
        """
        if not gate_config.enabled:
            return []
        caps: list[tuple[Verdict, str]] = []
        for risk in risk_factors:
            cap: Verdict | None = None
            if risk.gate is not None:
                named = getattr(gate_config, risk.gate, None)
                if isinstance(named, Verdict):
                    cap = named
            if cap is None:
                cap = _SEVERITY_CAP.get(risk.severity)
            if cap is not None:
                caps.append((cap, risk.description))
        return caps
