"""Launch the local Fiori-styled web UI for running assessments against saved systems.

Usage:
    . .\\activate_env.ps1
    python.exe webapp.py
    -> open http://127.0.0.1:5000

Runs on localhost only. This is a consultant-facing tool for demoing/reviewing
results with a customer -- it is never deployed into a customer environment.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from webapp.server import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
