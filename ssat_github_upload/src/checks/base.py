"""Shared result type + registry for assessment checks.

Every check module exposes a module-level ``CHECK`` (a ``CheckSpec``) and a
``collect(connector, config) -> CheckResult`` function. This first pass is
extraction-only: a CheckResult carries the raw findings pulled from the SAP
system plus factual counts, but no risk/maturity score or remediation text --
that scoring layer is a later phase per the Automation Philosophy in
SAP_Security_Framework_Assessment_Context.md.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RiskTile:
    """Declares one KPI-row tile this check can surface on the results dashboard.

    `extract` reads the check's own `summary` dict and returns the value to display (a
    number, or a short fixed string like "Open"/"Disabled") -- or a falsy value (None,
    0, "") when this run doesn't warrant a tile. Keeping this next to the check's own
    definition, instead of in a separate hardcoded list in the web UI's JS, means a new
    check's KPI tile ships in the same file as the check itself: nothing else to
    remember to update, and nothing to silently go missing from the dashboard.
    """

    label: str
    severity: str  # "crit" | "warn"
    extract: Callable[[dict[str, Any]], Any]


@dataclass
class CheckSpec:
    check_id: str          # matches the Detailed Checklist, e.g. "USR-004"
    domain: str             # assessment domain / checklist section
    question: str           # the assessment question being answered
    data_source: str        # SAP tables / function modules / services used
    collection_method: str  # short description of how the data is pulled
    scope: str = "client-specific"  # "client-specific" (only reflects the connected
    # client -- table carries MANDT, e.g. USR02/AGR_*) or "system-wide" (same
    # result regardless of which client you connect through, e.g. CVERS/RFCDES/
    # profile parameters). Confirmed per table via DDIF_FIELDINFO_GET, not assumed.
    risk_tiles: list[RiskTile] = field(default_factory=list)


@dataclass
class CheckResult:
    check_id: str
    domain: str
    question: str
    data_source: str
    collection_method: str
    system_id: str
    collected_at: str
    scope: str = "client-specific"
    findings: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "domain": self.domain,
            "question": self.question,
            "data_source": self.data_source,
            "collection_method": self.collection_method,
            "system_id": self.system_id,
            "collected_at": self.collected_at,
            "scope": self.scope,
            "record_count": len(self.findings),
            "summary": self.summary,
            "findings": self.findings,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckResult":
        return cls(
            check_id=data["check_id"],
            domain=data["domain"],
            question=data["question"],
            data_source=data["data_source"],
            collection_method=data["collection_method"],
            system_id=data["system_id"],
            collected_at=data["collected_at"],
            scope=data.get("scope", "client-specific"),
            findings=data.get("findings", []),
            summary=data.get("summary", {}),
            errors=data.get("errors", []),
        )


def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


_REGISTRY: dict[str, Callable[..., CheckResult]] = {}
_SPECS: dict[str, CheckSpec] = {}


def register(spec: CheckSpec) -> Callable[[Callable[..., CheckResult]], Callable[..., CheckResult]]:
    def decorator(fn: Callable[..., CheckResult]) -> Callable[..., CheckResult]:
        _REGISTRY[spec.check_id] = fn
        _SPECS[spec.check_id] = spec
        return fn

    return decorator


def all_check_ids() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_check(check_id: str) -> Callable[..., CheckResult]:
    return _REGISTRY[check_id]


def get_spec(check_id: str) -> CheckSpec:
    return _SPECS[check_id]
