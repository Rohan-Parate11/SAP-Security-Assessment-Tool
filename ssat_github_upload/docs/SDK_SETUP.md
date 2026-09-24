# Setting up pyrfc (one-time, per machine)

`pyrfc` is a C extension that links against SAP's licensed **NetWeaver RFC SDK**.
It is not on PyPI as an installable wheel (every release there is yanked or
Python-incompatible), but SAP publishes prebuilt Windows wheels on GitHub
releases that sidestep needing a compiler entirely. That's the path below;
building from source (needs Microsoft C++ Build Tools) is the fallback if no
matching prebuilt wheel exists for your Python version/OS.

## 1. Prerequisites

- SAP Support Portal access (S-user with a download entitlement for NW RFC SDK).
- The project venv already created at `.venv` (Python 3.11 64-bit).

## 2. Download the SDK

1. Go to https://support.sap.com/ -> **Software Downloads**.
2. Search **"SAP NW RFC SDK"** (or browse Installations and Upgrades -> By
   Alphabetical Index -> **N** -> SAP NW RFC SDK).
3. Pick the **Windows on x64 64bit** package matching a kernel release equal
   to or newer than your target SAP system's kernel (a newer SDK is
   generally backward-compatible with older kernels).
4. Extract the ZIP into the project's `sdk\` folder, e.g.
   `sdk\nwrfc750P_16-70002755\nwrfcsdk` (already done for this project -- confirmed
   x64, with `lib`/`include`/`bin`/`demo`/`doc`).

   This SDK is SAP-licensed software tied to your S-user. Don't commit it to
   git or share this project folder externally with the SDK still inside it.

## 3. Set environment variables (project-scoped, not machine-wide)

`activate_env.ps1` at the project root sets `SAPNWRFC_HOME` and prepends the
SDK's `lib` folder + the venv's `Scripts` folder to `PATH`, scoped to the
current PowerShell session only:

```powershell
cd "C:\Users\rohan.parate\Downloads\AI Automations\SAP Security Assessment Tool"
. .\activate_env.ps1
```

Run this once per new PowerShell session before using the venv or pyrfc.

## 4. Install pyrfc

**Option A -- prebuilt wheel (no compiler needed, used for this project):**

SAP's archived PyRFC repo publishes wheels for cp38-cp312 on win_amd64.
Match the filename to your venv's Python version (this project is cp311):

```powershell
python.exe -m pip install "https://github.com/SAP-archive/PyRFC/releases/download/v3.3.1/pyrfc-3.3.1-cp311-cp311-win_amd64.whl"
```

Browse https://github.com/SAP-archive/PyRFC/releases for other Python
versions/platforms if you rebuild the venv on a different interpreter.

**Option B -- build from source (only if no matching wheel exists):**

This requires **Microsoft C++ Build Tools** (Visual Studio Build Tools,
"Desktop development with C++" workload) to compile the Cython extension:

```powershell
python.exe -m pip install cython wheel setuptools
python.exe -m pip install "https://github.com/SAP-archive/PyRFC/archive/refs/heads/main.zip"
```

## 5. Verify

```powershell
python.exe -c "import pyrfc; print(pyrfc.__version__)"
```

If this prints a version with no import error, `src/connectors/rfc_connector.py`
will work as-is -- it imports `pyrfc` lazily inside `connect()`, so nothing
else in this project needs to change.

# Setting up the AI features (executive summary, remediation, Q&A)

The AI Insights tab (`src/ai/`) calls an LLM provider server-side -- the
default and only implemented provider today is Claude (Anthropic).

1. Get an API key from https://console.anthropic.com/ and set it as an
   environment variable before starting the server:

   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   python.exe src\webapp\server.py
   ```

   Without this set, the AI Insights tab still loads -- generating or asking
   returns a clear error asking you to set the key, rather than failing
   silently.

2. Optional overrides, also environment variables:
   - `AI_MODEL` -- a different model ID for whichever provider is active
     (Claude default: `claude-opus-5`; Gemini default: `gemini-flash-latest`;
     Groq default: `openai/gpt-oss-20b`).
   - `AI_PROVIDER` -- which provider implementation to use: `claude` (default),
     `gemini`, or `groq`. This is the lever a business/end user turns to point
     the tool at a different LLM vendor -- see `src/ai/providers/base.py` for
     the interface a new provider would implement.

Only aggregate/count-level data ever crosses into a call to any provider --
see `src/ai/sanitize.py`'s module docstring for what is stripped and why.

## Using Google Gemini instead of Claude (free tier)

Gemini is a free-tier alternative to Claude -- lower cost (free, rate-limited)
but noticeably lower writing/reasoning quality for the executive summary and
remediation guidance. Also note: Google's free tier may use your prompts to
improve their products unless you're on a paid tier -- read
https://ai.google.dev/gemini-api/terms before sending real assessment data,
even though only aggregate/count-level data is ever sent (see above).

1. Go to https://aistudio.google.com/ -> **Get API key** and create one (no
   credit card required for the free tier).
2. Set both env vars before starting the server:

   ```powershell
   $env:AI_PROVIDER = "gemini"
   $env:GEMINI_API_KEY = "..."
   python.exe src\webapp\server.py
   ```

Switch back to Claude at any time by unsetting `AI_PROVIDER` (or setting it
back to `claude`) and restarting the server -- no code changes either way.

## Using Groq instead of Claude (free tier)

Groq is another free-tier alternative -- runs fast, open-weight models
(default: `openai/gpt-oss-20b`). Like Gemini, quality is lower than Claude
for nuanced writing, and there's no vendor-native schema-constrained JSON mode
(this provider validates the model's JSON output itself, so remediation
generation can occasionally fail validation on a weaker model where Claude/
Gemini wouldn't -- retry if that happens).

1. Go to https://console.groq.com/keys and sign in (Google/GitHub/email --
   free, no credit card required for the free tier).
2. Click **Create API Key**, name it, and copy the value (`gsk_...`).
3. Set env vars before starting the server:

   ```powershell
   $env:AI_PROVIDER = "groq"
   $env:GROQ_API_KEY = "gsk_..."
   python.exe src\webapp\server.py
   ```

# Setting up the PDF assessment report (one-time)

The "Download PDF Report" button (AI Insights tab) renders an HTML report through
headless Chromium via Playwright. One-time setup, after `pip install -r requirements.txt`:

```powershell
python.exe -m playwright install chromium
```

**If this fails with `self-signed certificate in certificate chain`:** this network is
behind a TLS-inspecting corporate proxy (on this machine, Netskope) that re-signs HTTPS
traffic with its own root CA -- the same root cause behind the earlier `truststore` fix
in `src/ai/__init__.py`, but that fix only covers Python's own SSL context; Playwright's
installer is a separate Node.js process with its own trust store. Fix:

1. Find the proxy's root CA in the Windows certificate store (PowerShell):
   ```powershell
   Get-ChildItem -Path Cert:\CurrentUser\Root | Where-Object { $_.Subject -match "Netskope|Zscaler|<your proxy>" }
   ```
2. Export it to a PEM file and point Node at it for the install:
   ```powershell
   $cert = Get-ChildItem Cert:\CurrentUser\Root | Where-Object Thumbprint -eq "<thumbprint from step 1>"
   $b64 = [System.Convert]::ToBase64String($cert.RawData, [System.Base64FormattingOptions]::InsertLineBreaks)
   "-----BEGIN CERTIFICATE-----`r`n$b64`r`n-----END CERTIFICATE-----" | Out-File "$env:USERPROFILE\.proxy-ca.pem" -Encoding ascii
   $env:NODE_EXTRA_CA_CERTS = "$env:USERPROFILE\.proxy-ca.pem"
   python.exe -m playwright install chromium
   ```

Once installed, no further setup is needed -- `output/pdf_report.py` launches the same
bundled Chromium on every PDF request; `NODE_EXTRA_CA_CERTS` is only needed for this
one-time install step, not at runtime.
