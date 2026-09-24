"""Local web UI for running the SAP Security Assessment Tool against saved
customer systems. Runs on localhost only -- this is a consultant-facing tool,
never deployed into a customer environment (see project decision).

Usage:
    . .\\activate_env.ps1
    python.exe src\\webapp\\server.py
    -> open http://127.0.0.1:5000
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from flask import Flask, jsonify, request, send_file, send_from_directory  # noqa: E402

import checks  # noqa: E402  (registers check modules so CheckResult round-trips cleanly)
from ai.errors import AIProviderError  # noqa: E402
from ai.exec_summary import generate_executive_summary  # noqa: E402
from ai.providers import get_provider  # noqa: E402
from ai.qa import answer_question  # noqa: E402
from ai.remediation import generate_remediation  # noqa: E402
from checks.base import now_iso  # noqa: E402
from output.assessment_criteria import write_assessment_criteria  # noqa: E402
from output.pdf_report import render_pdf_bytes  # noqa: E402
from webapp import connection_test, gateway_detect, job_runner, systems_store  # noqa: E402
from webapp.run_summary import build_run_summary as _run_summary, posture_counts as _posture_counts  # noqa: E402

_OUTPUT_DIR = _SRC_DIR.parent / "output"

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.get("/")
def index():
    return send_from_directory(app.template_folder, "index.html")


# -- systems -----------------------------------------------------------------

ENVIRONMENTS = ["Sandbox", "Development", "Quality", "Production"]


def _build_profile(body: dict) -> tuple[dict | None, str | None]:
    required = ["label", "system_id", "ashost", "sysnr", "client", "user", "environment"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return None, f"Missing required field(s): {', '.join(missing)}"
    if body["environment"] not in ENVIRONMENTS:
        return None, f"environment must be one of: {', '.join(ENVIRONMENTS)}"

    profile = {
        "label": body["label"],
        "environment": body["environment"],
        "system_id": body["system_id"],
        "ashost": body["ashost"],
        "sysnr": body["sysnr"],
        "client": body["client"],
        "user": body["user"],
        "lang": body.get("lang", "EN"),
    }
    odata = body.get("odata")
    if odata and odata.get("base_url"):
        profile["odata"] = {
            "base_url": odata["base_url"],
            "client": odata.get("client", profile["client"]),
            "user": odata.get("user", profile["user"]),
            "verify_ssl": bool(odata.get("verify_ssl", True)),
        }
    return profile, None


@app.get("/api/systems")
def list_systems():
    return jsonify(systems_store.list_systems())


@app.post("/api/systems")
def add_system():
    profile, error = _build_profile(request.get_json(force=True))
    if error:
        return jsonify({"error": error}), 400
    saved = systems_store.add_system(profile)
    return jsonify(saved), 201


@app.put("/api/systems/<key>")
def edit_system(key: str):
    if systems_store.get_system(key) is None:
        return jsonify({"error": "Unknown system"}), 404
    profile, error = _build_profile(request.get_json(force=True))
    if error:
        return jsonify({"error": error}), 400
    updated = systems_store.update_system(key, profile)
    return jsonify(updated)


@app.delete("/api/systems/<key>")
def delete_system(key: str):
    ok = systems_store.delete_system(key)
    return jsonify({"deleted": ok})


@app.post("/api/systems/test-connection")
def test_connection_route():
    body = request.get_json(force=True) or {}
    required = ["ashost", "sysnr", "client", "user", "password"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
    try:
        result = connection_test.test_connection(
            ashost=body["ashost"],
            sysnr=body["sysnr"],
            client=body["client"],
            user=body["user"],
            passwd=body["password"],
            lang=body.get("lang", "EN"),
        )
    except connection_test.ConnectionTestError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.post("/api/systems/detect-gateway")
def detect_gateway():
    body = request.get_json(force=True) or {}
    required = ["ashost", "sysnr", "client", "user", "password"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
    try:
        result = gateway_detect.detect_gateway_url(
            ashost=body["ashost"],
            sysnr=body["sysnr"],
            client=body["client"],
            user=body["user"],
            passwd=body["password"],
            lang=body.get("lang", "EN"),
        )
    except gateway_detect.GatewayDetectionError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.get("/api/systems/<key>/latest")
def latest_run(key: str):
    run_dir = job_runner.latest_run_dir(key)
    if run_dir is None:
        return jsonify(None)
    return jsonify(_run_summary(run_dir))


@app.get("/api/systems/<key>/runs")
def list_runs(key: str):
    entries = []
    for run_dir in job_runner.run_dirs_for_system(key):
        summary = _run_summary(run_dir)
        entries.append(
            {
                "run_name": summary["run_name"],
                "run_at": summary["meta"].get("run_at"),
                "posture": _posture_counts(summary),
            }
        )
    return jsonify(entries)


@app.get("/api/runs/<run_name>/summary")
def run_summary_by_name(run_name: str):
    run_dir = _OUTPUT_DIR / run_name
    if not (run_dir / "meta.json").exists():
        return jsonify({"error": "Run not found"}), 404
    return jsonify(_run_summary(run_dir))


# -- AI insights (executive summary, remediation, Q&A) ------------------------
# Data-boundary and provider-agnostic design: see ai/sanitize.py and
# ai/providers/base.py. Generated summary+remediation are cached to
# ai_insights.json (regenerated only on explicit request) since every call
# costs real money; Q&A is answered live per question and appended to
# ai_qa_log.json, mirroring rfc_trace.json's "make backend calls visible for
# troubleshooting" precedent.

def _run_dir_or_404(run_name: str) -> Path | None:
    run_dir = _OUTPUT_DIR / run_name
    return run_dir if (run_dir / "meta.json").exists() else None


@app.get("/api/runs/<run_name>/ai/insights")
def get_ai_insights(run_name: str):
    run_dir = _run_dir_or_404(run_name)
    if run_dir is None:
        return jsonify({"error": "Run not found"}), 404
    insights_path = run_dir / "ai_insights.json"
    if not insights_path.exists():
        return jsonify(None)
    return jsonify(json.loads(insights_path.read_text(encoding="utf-8")))


@app.post("/api/runs/<run_name>/ai/generate")
def generate_ai_insights(run_name: str):
    run_dir = _run_dir_or_404(run_name)
    if run_dir is None:
        return jsonify({"error": "Run not found"}), 404
    insights_path = run_dir / "ai_insights.json"
    force = bool((request.get_json(silent=True) or {}).get("force"))
    if insights_path.exists() and not force:
        return jsonify(json.loads(insights_path.read_text(encoding="utf-8")))

    run_summary = _run_summary(run_dir)
    try:
        provider = get_provider()
        # Sequential, not parallel: the exec-summary call warms the provider's
        # prompt cache for this run's context, so the remediation call (same
        # context) reads from cache instead of paying to write it twice.
        summary_text = generate_executive_summary(run_summary, provider=provider)
        remediation_items = generate_remediation(run_summary, provider=provider)
    except AIProviderError as exc:
        return jsonify({"error": str(exc)}), 400

    insights = {
        "executive_summary": summary_text,
        "remediation": remediation_items,
        "generated_at": now_iso(),
        "provider": provider.name,
    }
    insights_path.write_text(json.dumps(insights, indent=2), encoding="utf-8")

    # Best-effort: re-render the cached PDF so a download right after Regenerate is still
    # instant (see download_pdf_report below). A rendering failure here must not fail this
    # response -- the download route falls back to rendering on demand if the cache is stale/missing.
    try:
        (run_dir / "report.pdf").write_bytes(render_pdf_bytes(run_summary, insights))
    except Exception:  # noqa: BLE001
        pass

    return jsonify(insights)


@app.post("/api/runs/<run_name>/ai/ask")
def ask_ai_question(run_name: str):
    run_dir = _run_dir_or_404(run_name)
    if run_dir is None:
        return jsonify({"error": "Run not found"}), 404
    body = request.get_json(force=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    history = body.get("history") or []

    run_summary = _run_summary(run_dir)
    try:
        answer = answer_question(run_summary, question, history=history)
    except AIProviderError as exc:
        return jsonify({"error": str(exc)}), 400

    log_path = run_dir / "ai_qa_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    log.append({"question": question, "answer": answer, "asked_at": now_iso()})
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    return jsonify({"answer": answer})


@app.get("/api/dashboard")
def dashboard():
    systems = systems_store.list_systems()
    entries = []
    totals = {"critical": 0, "warning": 0, "clean": 0, "errored": 0}
    systems_with_critical = 0
    systems_never_run = 0
    for sys in systems:
        run_dir = job_runner.latest_run_dir(sys["key"])
        posture = None
        run_at = None
        run_name = None
        if run_dir is not None:
            summary = _run_summary(run_dir)
            posture = _posture_counts(summary)
            run_at = summary["meta"].get("run_at")
            run_name = summary["run_name"]
            totals["critical"] += posture["critical"]
            totals["warning"] += posture["warning"]
            totals["clean"] += posture["clean"]
            totals["errored"] += posture["errored"]
            if posture["critical"] > 0:
                systems_with_critical += 1
        else:
            systems_never_run += 1
        entries.append(
            {
                "key": sys["key"],
                "label": sys["label"],
                "system_id": sys.get("system_id"),
                "environment": sys.get("environment"),
                "run_name": run_name,
                "run_at": run_at,
                "posture": posture,
            }
        )
    # Riskiest system first: most critical findings, then most warnings, then never-assessed
    # systems last (nothing to sort them by).
    entries.sort(
        key=lambda e: (
            e["posture"] is None,
            -(e["posture"]["critical"] if e["posture"] else 0),
            -(e["posture"]["warning"] if e["posture"] else 0),
        )
    )
    return jsonify(
        {
            "systems": entries,
            "totals": totals,
            "systems_total": len(systems),
            "systems_with_critical": systems_with_critical,
            "systems_never_run": systems_never_run,
        }
    )


# -- runs ----------------------------------------------------------------------

@app.post("/api/systems/<key>/run")
def trigger_run(key: str):
    profile = systems_store.get_system(key)
    if profile is None:
        return jsonify({"error": "Unknown system"}), 404
    password = (request.get_json(force=True) or {}).get("password")
    if not password:
        return jsonify({"error": "Password is required"}), 400

    job_id = job_runner.start_job(key, profile, password)
    return jsonify({"job_id": job_id}), 202


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = job_runner.get_job(job_id)
    if job is None:
        return jsonify({"error": "Unknown job"}), 404
    if job.get("run_dir"):
        job = dict(job)
        job["result_summary"] = _run_summary(Path(job["run_dir"]))
    return jsonify(job)


@app.get("/api/runs/<run_name>/results")
def run_results(run_name: str):
    run_dir = _OUTPUT_DIR / run_name
    all_results_path = run_dir / "all_results.json"
    if not all_results_path.exists():
        return jsonify({"error": "Run not found"}), 404
    return jsonify(json.loads(all_results_path.read_text(encoding="utf-8")))


@app.get("/api/criteria/download")
def download_criteria():
    # Not run-specific -- explains the checks themselves, so it's generated fresh each request
    # rather than tied to any one system's output folder.
    buf = io.BytesIO()
    write_assessment_criteria(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="SAP_Security_Assessment_Criteria.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/runs/<run_name>/download")
def download_excel(run_name: str):
    run_dir = _OUTPUT_DIR / run_name
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return jsonify({"error": "Run not found"}), 404
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return send_from_directory(run_dir, meta["excel_filename"], as_attachment=True)


@app.get("/api/runs/<run_name>/report/pdf")
def download_pdf_report(run_name: str):
    run_dir = _run_dir_or_404(run_name)
    if run_dir is None:
        return jsonify({"error": "Run not found"}), 404
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    download_name = f"SAP_Security_Assessment_Report_{meta.get('system_id', run_name)}.pdf"

    cached_path = run_dir / "report.pdf"
    if cached_path.exists():
        # Rendered automatically once the run's AI Insights were generated (job_runner.py's
        # post-run step, or generate_ai_insights above) -- no Playwright launch on this request
        # path, so the download is instant.
        return send_file(cached_path, as_attachment=True, download_name=download_name, mimetype="application/pdf")

    insights_path = run_dir / "ai_insights.json"
    if not insights_path.exists():
        return jsonify({"error": "Generate AI Insights for this run first, then download the PDF report."}), 400

    # Fallback for a run from before this caching existed, or where auto-generation failed:
    # render on demand, same as this route originally always did.
    run_summary = _run_summary(run_dir)
    ai_insights = json.loads(insights_path.read_text(encoding="utf-8"))
    pdf_bytes = render_pdf_bytes(run_summary, ai_insights)
    return send_file(
        io.BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    # threaded=True: an AI Insights generation call can take several seconds,
    # and without this a single-threaded dev server would block every other
    # request (run-progress polling, other tabs) for that whole window.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
