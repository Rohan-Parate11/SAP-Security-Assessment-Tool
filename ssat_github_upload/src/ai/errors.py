"""Shared exception for the AI layer, in the same style as
webapp/connection_test.py's ConnectionTestError -- one exception type, raised
by provider implementations and feature modules, caught at the Flask route.
"""

from __future__ import annotations


class AIProviderError(RuntimeError):
    pass
