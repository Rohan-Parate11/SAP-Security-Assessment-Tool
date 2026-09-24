"""Runs a full assessment against a saved system profile in a background thread,
so the web UI can show live per-check progress instead of blocking on one long request.
The password is only ever held in memory for the lifetime of the job -- never written to disk.
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from ai.errors import AIProviderError  # noqa: E402
from ai.exec_summary import generate_executive_summary  # noqa: E402
from ai.providers import get_provider  # noqa: E402
from ai.remediation import generate_remediation  # noqa: E402
from checks.base import all_check_ids, now_iso  # noqa: E402
from connectors import RFCConnectionError, RFCConnector  # noqa: E402
from output import write_excel, write_json  # noqa: E402
from output.pdf_report import render_pdf_bytes  # noqa: E402
from run_assessment import run_checks  # noqa: E402
from webapp.run_summary import build_run_summary  # noqa: E402

_OUTPUT_DIR = _SRC_DIR.parent / "output"

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _init_progress() -> dict[str, str]:
    return {cid: "pending" for cid in all_check_ids()}


def start_job(system_key: str, system_profile: dict[str, Any], password: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "status": "running",
            "progress": _init_progress(),
            "system_label": system_profile.get("label", system_profile.get("system_id", "")),
            "run_dir": None,
            "error": None,
            "phase": None,  # human-readable sub-status shown once all checks are done (AI/PDF generation)
            "ai_error": None,  # set if the automatic AI insights/PDF step below failed -- the run itself still succeeds
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }

    thread = threading.Thread(
        target=_run, args=(job_id, system_key, dict(system_profile), password), daemon=True
    )
    thread.start()
    return job_id


def run_dirs_for_system(system_key: str) -> list[Path]:
    """All completed run directories for a system, newest first."""
    if not _OUTPUT_DIR.exists():
        return []
    candidates = []
    for d in _OUTPUT_DIR.iterdir():
        meta_path = d / "meta.json"
        if d.is_dir() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("system_key") == system_key:
                candidates.append(d)
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def latest_run_dir(system_key: str) -> Path | None:
    dirs = run_dirs_for_system(system_key)
    return dirs[0] if dirs else None


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _set(job_id: str, **fields: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _set_progress(job_id: str, check_id: str, status: str) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"][check_id] = status


def _run(job_id: str, system_key: str, profile: dict[str, Any], password: str) -> None:
    config = dict(profile)
    config["passwd"] = password
    odata_cfg = config.get("odata")
    if isinstance(odata_cfg, dict) and not odata_cfg.get("passwd"):
        odata_cfg = dict(odata_cfg)
        odata_cfg["passwd"] = password
        config["odata"] = odata_cfg

    connector = RFCConnector(
        ashost=config["ashost"],
        sysnr=config["sysnr"],
        client=config["client"],
        user=config["user"],
        passwd=config["passwd"],
        lang=config.get("lang", "EN"),
        system_id=config.get("system_id"),
    )

    def on_progress(check_id: str, status: str, result) -> None:  # noqa: ANN001
        _set_progress(job_id, check_id, status)

    try:
        connector.connect()
    except RFCConnectionError as exc:
        _set(job_id, status="error", error=f"Connection failed: {exc}")
        return

    try:
        results = run_checks(connector, config, all_check_ids(), on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001
        _set(job_id, status="error", error=str(exc))
        return
    finally:
        connector.close()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _OUTPUT_DIR / f"{connector.system_id or 'assessment'}_{timestamp}"
    write_json(results, run_dir)
    excel_path = run_dir / f"SAP_Security_Assessment_{connector.system_id or 'results'}_{timestamp}.xlsx"
    write_excel(results, excel_path)

    # Every RFC call made during this run (see RFCConnector.trace) -- surfaced in the web UI's
    # Logs tab so a consultant can see exactly what was executed against the backend and what it
    # returned, not just each check's own summary sentence.
    trace = getattr(connector, "trace", None)
    if trace is not None:
        (run_dir / "rfc_trace.json").write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")

    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "system_key": system_key,
                "system_label": profile.get("label", ""),
                "system_id": connector.system_id,
                "client": profile.get("client"),
                "run_at": datetime.now().isoformat(timespec="seconds"),
                "excel_filename": excel_path.name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Auto-generate AI Insights + the PDF report right away, so the download in the AI Insights
    # tab is instant instead of a separate, later action -- best-effort: any failure here (a
    # rate-limited/high-demand provider, a transient network error) must not fail the run itself.
    # The AI Insights tab's existing "Generate AI Insights" button is the fallback if this fails.
    _set(job_id, phase="Generating AI insights...")
    run_summary = build_run_summary(run_dir)
    ai_insights = None
    try:
        provider = get_provider()
        summary_text = generate_executive_summary(run_summary, provider=provider)
        remediation_items = generate_remediation(run_summary, provider=provider)
        ai_insights = {
            "executive_summary": summary_text,
            "remediation": remediation_items,
            "generated_at": now_iso(),
            "provider": provider.name,
        }
        (run_dir / "ai_insights.json").write_text(json.dumps(ai_insights, indent=2), encoding="utf-8")
    except AIProviderError as exc:
        _set(job_id, ai_error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _set(job_id, ai_error=str(exc))

    if ai_insights is not None:
        _set(job_id, phase="Rendering PDF report...")
        try:
            (run_dir / "report.pdf").write_bytes(render_pdf_bytes(run_summary, ai_insights))
        except Exception as exc:  # noqa: BLE001
            _set(job_id, ai_error=f"Report rendering failed: {exc}")

    _set(job_id, status="done", run_dir=str(run_dir), phase=None)
