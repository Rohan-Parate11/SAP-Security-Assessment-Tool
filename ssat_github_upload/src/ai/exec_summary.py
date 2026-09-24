"""Auto-generated executive summary narrative for a completed assessment run.
Same shape as webapp/connection_test.py: one function, provider-agnostic --
takes an optional `provider` so callers (and tests) can inject any LLMProvider.
"""

from __future__ import annotations

import json

from ai.providers import LLMProvider, get_provider
from ai.sanitize import build_ai_safe_context

# Kept separate from the (large, cacheable) context JSON -- see LLMProvider's
# docstring on why context/instruction are two different arguments.
_INSTRUCTION = """\
You are a senior SAP security consultant writing the executive summary section \
of an assessment report. Using only the assessment data provided above, write \
3-5 short paragraphs in plain, direct prose (no headings, no bullet lists) that \
a client executive who is not SAP-technical can read in under a minute. Cover: \
overall posture, the most significant risks (by severity, referencing counts), \
and the general shape of remediation effort needed. Only reference check_ids, \
counts, and key findings present in the data -- never invent a finding, a \
number, or a specific person's name. You do not have access to individual \
usernames or record-level detail; if that level of detail matters, say the \
reader should consult the Descriptive tab or the Excel report.
"""


def generate_executive_summary(run_summary: dict, provider: LLMProvider | None = None) -> str:
    provider = provider or get_provider()
    safe_context = build_ai_safe_context(run_summary)
    return provider.generate_text(
        context=json.dumps(safe_context, indent=2),
        instruction=_INSTRUCTION,
    ).strip()
