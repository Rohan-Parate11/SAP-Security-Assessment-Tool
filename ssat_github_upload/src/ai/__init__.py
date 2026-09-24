"""AI-assisted layer: executive summary narrative, remediation guidance, and
Q&A over a completed run's (sanitized) results. See ai.sanitize for the data
boundary and ai.providers for the LLM vendor abstraction.
"""

from __future__ import annotations

import truststore

# On a network behind a TLS-inspecting corporate proxy, outbound HTTPS to a
# provider's API can fail with "self-signed certificate in certificate chain"
# -- the proxy re-signs traffic with its own internal root CA, which isn't in
# Python's bundled certifi CA list. The OS-native certificate store (Windows
# cert store here) almost always already trusts that proxy's root CA (IT
# deploys it via policy so browsers work), so switching to it via truststore
# resolves this without sourcing/installing the corporate CA ourselves.
# Applied once, package-wide, since any provider's domain could be affected
# depending on the network's allowlist -- confirmed necessary for Groq's API
# on this machine even though Claude's and Gemini's happened to work without it.
truststore.inject_into_ssl()
