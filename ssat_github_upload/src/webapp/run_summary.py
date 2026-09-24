"""Builds the one run-summary dict shape (meta + checks + kpi_tiles) that every
consumer of a completed run -- server.py's routes, job_runner.py's post-run AI/PDF
step, and the AI feature modules -- reads from. Pulled out of server.py so
job_runner.py can build it too, without importing the Flask app module.
"""

from __future__ import annotations

import json
from pathlib import Path

from checks.base import CheckResult, get_spec

from output.narrative import key_finding

_SEVERITY_ORDER = {"crit": 0, "warn": 1, "good": 2}


def _key_finding_safe(r: dict) -> str:
    # A run saved before a check_id/schema change (e.g. the ROL-005/ROL-006 rename) can have a
    # check_id whose stored summary/findings shape no longer matches that renderer's expectations.
    # Fall back to a generic finding rather than 500ing the whole run summary over one stale check.
    try:
        return key_finding(CheckResult.from_dict(r))
    except Exception:
        return f"{r.get('record_count', 0)} record(s) collected."


def kpi_tiles(results: list[dict]) -> list[dict]:
    # Each check's own module declares its risk_tiles (see checks/base.py's RiskTile) --
    # this just runs them against that check's stored summary. A new check with a
    # risk_tiles entry shows up here automatically; nothing in the web layer needs to
    # know about it. A stale historical run whose check_id no longer exists in the
    # current registry (e.g. a pre-rename check_id) contributes no tiles rather than
    # 500ing the whole run summary.
    tiles = []
    for r in results:
        try:
            spec = get_spec(r["check_id"])
        except KeyError:
            continue
        for rt in spec.risk_tiles:
            try:
                value = rt.extract(r.get("summary") or {})
            except Exception:
                continue
            if not value:
                continue
            tiles.append({"value": value, "label": rt.label, "cls": rt.severity, "check_id": r["check_id"]})
    # Priority order = severity first, then magnitude within a severity tier (a bigger finding
    # of the same severity is the more urgent one to address first). A tile whose value isn't a
    # number (e.g. SYS-004's "Open") is a definitive binary fact rather than a scaled count, so
    # it sorts to the front of its tier rather than competing numerically with counted findings.
    tiles.sort(key=lambda t: (_SEVERITY_ORDER.get(t["cls"], 3), -t["value"] if isinstance(t["value"], (int, float)) else float("-inf")))
    return tiles


def posture_counts(summary: dict) -> dict:
    # Mirrors the web UI's Visual-tab "Assessment Posture" donut (app.js's vizPostureDonuts):
    # every check bucketed into the most severe risk tile it triggered, defaulting to clean.
    tiles = summary.get("kpi_tiles") or []
    crit_ids = {t["check_id"] for t in tiles if t["cls"] == "crit"}
    warn_ids = {t["check_id"] for t in tiles if t["cls"] == "warn"}
    critical = warning = clean = errored = 0
    for c in summary.get("checks") or []:
        if c["check_id"] in crit_ids:
            critical += 1
        elif c["check_id"] in warn_ids:
            warning += 1
        else:
            clean += 1
        if c.get("error_count", 0) > 0:
            errored += 1
    return {"critical": critical, "warning": warning, "clean": clean, "errored": errored}


def build_run_summary(run_dir: Path) -> dict:
    meta_path = run_dir / "meta.json"
    all_results_path = run_dir / "all_results.json"
    trace_path = run_dir / "rfc_trace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    results = json.loads(all_results_path.read_text(encoding="utf-8")) if all_results_path.exists() else []
    # Absent for any run captured before this tracing was added -- the Logs tab just shows
    # nothing below the check-level summary lines for those older runs, rather than erroring.
    rfc_trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else []
    return {
        "run_name": run_dir.name,
        "meta": meta,
        "kpi_tiles": kpi_tiles(results),
        "rfc_trace": rfc_trace,
        "checks": [
            {
                "check_id": r["check_id"],
                "domain": r["domain"],
                "question": r["question"],
                "scope": r.get("scope"),
                "record_count": r["record_count"],
                "summary": r["summary"],
                "error_count": len(r.get("errors", [])),
                "key_finding": _key_finding_safe(r),
                "collected_at": r.get("collected_at"),
                "errors": r.get("errors", []),
            }
            for r in results
        ],
    }
