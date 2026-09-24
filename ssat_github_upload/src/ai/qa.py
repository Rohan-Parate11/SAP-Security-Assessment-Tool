"""Natural-language Q&A over a completed run's (sanitized) results. Each call
is independent against the same run context -- `history` (prior turns in this
viewing session, not persisted across sessions) is folded into the
instruction text rather than a real multi-turn message list, keeping the
LLMProvider interface's two-string shape uniform across all three features.
"""

from __future__ import annotations

import json

from ai.providers import LLMProvider, get_provider
from ai.sanitize import build_ai_safe_context

_INSTRUCTION_TEMPLATE = """\
You are a senior SAP security consultant answering a question about the \
assessment data provided above. Answer only from that data -- reference \
check_ids and counts where relevant, and never invent a finding or a number \
that isn't present. You do not have access to individual usernames or \
record-level detail; if asked for that, say to check the Descriptive tab or \
the Excel report instead of guessing. Keep the answer conversational and \
under 150 words unless the question needs more.
{history_block}
New question: {question}
"""


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    turns = "\n".join(f"Q: {h['question']}\nA: {h['answer']}" for h in history)
    return f"\nPrevious questions in this session:\n{turns}\n"


def answer_question(
    run_summary: dict, question: str, history: list[dict] | None = None, provider: LLMProvider | None = None
) -> str:
    provider = provider or get_provider()
    safe_context = build_ai_safe_context(run_summary)
    instruction = _INSTRUCTION_TEMPLATE.format(
        history_block=_format_history(history or []),
        question=question,
    )
    return provider.generate_text(
        context=json.dumps(safe_context, indent=2),
        instruction=instruction,
    ).strip()
