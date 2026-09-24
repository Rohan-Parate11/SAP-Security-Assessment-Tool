"""LLM-assisted remediation guidance, one entry per flagged risk indicator
(the same set already surfaced as "Top Risk Indicators" in the Visual/
Descriptive tabs -- server.py's kpi_tiles) -- not every check, since most
checks that didn't cross a risk threshold have nothing to remediate.
"""

from __future__ import annotations

import json
from typing import Any

from ai.providers import LLMProvider, get_provider
from ai.sanitize import build_ai_safe_context

REMEDIATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "check_id": {"type": "string"},
                    "label": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["check_id", "label", "recommendation", "steps"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_INSTRUCTION = """\
You are a senior SAP security consultant writing remediation guidance. Using \
only the assessment data provided above, write one remediation entry for every \
entry in "kpi_tiles" (match by its check_id and label). For each: a short \
`recommendation` (1-2 sentences, what to do and why) and 2-5 concrete `steps` a \
customer's SAP Basis/security team could follow. Ground every recommendation in \
the specific counts and key_finding text for that check_id -- never invent a \
detail not present in the data. You do not have access to individual \
usernames; do not reference any by name.
"""


def generate_remediation(run_summary: dict, provider: LLMProvider | None = None) -> list[dict]:
    provider = provider or get_provider()
    safe_context = build_ai_safe_context(run_summary)
    if not safe_context["kpi_tiles"]:
        return []
    result = provider.generate_json(
        context=json.dumps(safe_context, indent=2),
        instruction=_INSTRUCTION,
        json_schema=REMEDIATION_SCHEMA,
    )
    return result["items"]
