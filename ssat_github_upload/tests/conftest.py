"""Puts src/ on sys.path so tests can `import ai...`, `import checks...`, etc.
-- same pattern webapp/server.py and webapp/job_runner.py already use to run
standalone from within src/webapp/.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
