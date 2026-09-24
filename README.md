# SAP Security Assessment Tool (SSAT)

An internal Bristlecone consulting tool that runs a set of read-only, non-invasive
security checks against a SAP system over RFC/OData, and presents the results in a
Fiori-styled web UI -- with Excel and AI-assisted PDF report generation for client
deliverables.

No configuration changes are ever made to the assessed system. Every check is a
read-only RFC/OData call.

## What it does

- **20 automated checks** across 8 assessment domains (see [Assessment domains](#assessment-domains-and-checks) below).
- **Fiori-styled web UI**: a dashboard across all your saved systems, and per-system
  Descriptive / Visual / Logs / History / AI Insights views.
- **Excel report** generation for every run, plus a client-ready **AI-assisted PDF
  report** (cover page, executive summary, risk heat map, detailed findings,
  remediation roadmap).
- **AI features** (optional): an auto-generated executive summary, remediation
  guidance per finding, and free-form natural-language Q&A over a run's results --
  built on a provider-agnostic interface, so you can point it at **Claude, Gemini,
  or Groq** without any code changes. Only aggregate/count-level data (never
  individual usernames or row-level records) is ever sent to an AI provider.
- **Run history & comparison**: every run is saved; compare any two runs for the
  same system to see what changed.

## Requirements

- **Windows** (the SAP NetWeaver RFC SDK's prebuilt Python wheel used here targets
  `win_amd64`; other platforms would need to build `pyrfc` from source).
- **Python 3.11** (64-bit).
- **SAP NetWeaver RFC SDK** -- licensed SAP software. You'll need SAP Support Portal
  / S-user access to download it (see [Step 3](#3-install-the-sap-netweaver-rfc-sdk)
  below). **This is never committed to this repo.**
- A SAP system and an RFC user with read-only authorization for the checks you want
  to run.
- *(Optional)* An API key for [Claude](https://console.anthropic.com/),
  [Gemini](https://aistudio.google.com/), or [Groq](https://console.groq.com/keys)
  if you want the AI Insights features.

## Setup

### 1. Clone and create a virtual environment

```powershell
git clone https://github.com/Rohan-Parate11/SAP-Security-Assessment-Tool.git
cd SAP-Security-Assessment-Tool
python -m venv .venv
```

### 2. Install Python dependencies

```powershell
.venv\Scripts\pip install -r requirements.txt
```

`pyrfc` is **not** in `requirements.txt` -- see the next step.

### 3. Install the SAP NetWeaver RFC SDK

`pyrfc` is a C extension that links against SAP's licensed NetWeaver RFC SDK, which
isn't distributed here or on PyPI.

1. Go to [support.sap.com](https://support.sap.com/) -> **Software Downloads** ->
   search **"SAP NW RFC SDK"**, and download the **Windows on x64 64bit** package.
2. Extract it into this project's `sdk\` folder (e.g. `sdk\nwrfc750P_xx\nwrfcsdk`,
   with `lib`/`include`/`bin` subfolders). This folder is gitignored -- it's
   SAP-licensed software tied to your S-user, never commit or share it.
3. Install the matching prebuilt `pyrfc` wheel (no compiler needed) -- for a
   Python 3.11 venv:
   ```powershell
   .venv\Scripts\pip install "https://github.com/SAP-archive/PyRFC/releases/download/v3.3.1/pyrfc-3.3.1-cp311-cp311-win_amd64.whl"
   ```
   Browse [SAP-archive/PyRFC releases](https://github.com/SAP-archive/PyRFC/releases)
   for a different Python version.

Full details, troubleshooting, and the build-from-source fallback are in
[`docs/SDK_SETUP.md`](docs/SDK_SETUP.md).

### 4. Activate the environment

`activate_env.ps1` points this PowerShell session at the SDK and the venv (scoped
to this project only, not machine-wide). Run this once per new terminal session,
before using the venv or `pyrfc`:

```powershell
. .\activate_env.ps1
```

It should print `SAPNWRFC_HOME = ...` and confirm the venv's `Scripts` folder was
added to `PATH`.

### 5. *(Optional)* Set up AI Insights

Without an API key, the app still runs fine -- the AI Insights tab just prompts you
to set one before generating anything. To enable it:

```powershell
$env:AI_PROVIDER = "claude"          # or "gemini" / "groq" -- default is "claude"
$env:ANTHROPIC_API_KEY = "sk-ant-..."  # matching key for whichever provider you picked
```

See [`docs/SDK_SETUP.md`](docs/SDK_SETUP.md) for how to get a free-tier Gemini or
Groq key instead of a paid Claude key, and for the full list of env vars.

### 6. *(Optional)* Install Playwright's Chromium, for the PDF report

```powershell
python.exe -m playwright install chromium
```

One-time, ~300MB. Only needed for the "Download PDF Report" feature -- Excel export
and everything else works without it.

### 7. Run it

```powershell
python.exe src\webapp\server.py
```

Then open **http://127.0.0.1:5000**. From there:

1. **Add System** (Home page) -- enter your SAP system's connection details.
   "Test Connection" before saving to confirm RFC connectivity.
2. Open the system and click **Run Assessment** -- enter the RFC password (held in
   memory only for the run, never written to disk).
3. Once it completes, browse results across the Descriptive / Visual / Logs tabs,
   generate AI Insights, and download the Excel or PDF report.

## Configuration files

| File | Purpose | Committed to git? |
|---|---|---|
| `src/config/connection.json.example` | Template for a standalone CLI-style run (see its own comments) | Yes (template only) |
| `src/config/connection.json` | Your real, local copy of the above | **No** -- gitignored |
| `src/config/systems.json` | Systems saved via the web UI's "Add System" | **No** -- gitignored, created automatically |
| `src/config/baseline_profile_parameters.json`, `critical_auth_objects.json`, `icf_denylist.json` | Generic SAP security baseline reference data used by the checks (not client-specific) | Yes |

A fresh clone starts with no saved systems -- add them through the web UI, or copy
`connection.json.example` to `connection.json` for the standalone script usage in
`regenerate_report.py`/`poc_connection_test.py`.

## Running tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

The test suite (AI feature logic, provider abstraction, sanitization, PDF report
data assembly) runs entirely against a `FakeProvider` and fixture data -- no API
key or SAP connection required.

## Assessment domains and checks

| Domain | Check ID | Question |
|---|---|---|
| SAP Landscape | LAN-001 | List all SAP components and versions. |
| SAP Landscape | LAN-002 | List all SAP systems and SID. |
| SAP Landscape | LAN-005 | Number of users per system? |
| SAP Landscape | LAN-007 | List all installed SAP product versions. |
| User Administration | USR-004 | Are dormant users reviewed? |
| User Administration | USR-007 | Standard users secured (SAP*, DDIC, EARLYWATCH)? |
| Roles & Authorizations | ROL-003 | Derived roles implemented? |
| Roles & Authorizations | ROL-005 | Unused roles identified? |
| Roles & Authorizations | ROL-006 | Critical authorization objects reviewed? |
| Privileged Access | PRV-001 | Who has SAP_ALL? |
| Privileged Access | PRV-002 | Who has SAP_NEW? |
| Privileged Access | PRV-003 | Who has S_DEVELOP? |
| System Hardening | SYS-001 | Profile parameters aligned with SAP recommendations? |
| System Hardening | SYS-002 | Security Audit Log enabled? |
| System Hardening | SYS-004 | Gateway security configured? |
| RFC & Interfaces | RFC-002 | Stored passwords reviewed? |
| RFC & Interfaces | RFC-003 | Trusted RFCs documented? |
| Fiori & Web | FIO-006 | Required ICF services only active? |
| Fiori & Web | FIO-007 | OData services reviewed? |
| SAP GRC | GRC-001 | Is SAP GRC implemented? |

## Project structure

```
src/
  checks/       One module per check (LAN-001, PRV-001, ...) -- pure extraction
                 logic, each declaring its domain, question, and risk tiles.
  connectors/    SAPConnector interface + RFCConnector (pyrfc) / OData implementations.
  ai/            Provider-agnostic LLM interface (ClaudeProvider / GeminiProvider /
                 GroqProvider / FakeProvider) and the 3 AI features (exec summary,
                 remediation, Q&A), plus the data-sanitization boundary.
  output/        Excel writer and the PDF report generator (Jinja2 + Playwright).
  webapp/        Flask app: server.py (routes), job_runner.py (background runs),
                 systems_store.py, static/ (app.js, style.css), templates/.
  config/        Reference data (baseline params, critical auth objects, ICF
                 denylist) + your local system/connection configs (gitignored).
tests/           pytest suite -- AI features, providers, sanitization, PDF report.
docs/            Setup guide (SDK_SETUP.md) and internal planning materials.
```

## Security notes

- RFC/OData passwords are **never written to disk** -- held in memory only for the
  duration of a run.
- `src/config/systems.json` and `connection.json` (real hostnames, IPs, RFC
  usernames) are gitignored; only the `.example` template is committed.
- The SAP NetWeaver RFC SDK (`sdk/`) is licensed software and is gitignored --
  every developer needs their own copy per [Step 3](#3-install-the-sap-netweaver-rfc-sdk).
- Only aggregate/count-level data ever crosses into an AI provider call -- see
  `src/ai/sanitize.py` for exactly what's stripped and why.

## Internal / confidential

This is an internal Bristlecone tool. The checked-in `Documents/` and `docs/`
folders include internal planning material and a real generated assessment output
-- treat this repository accordingly.
