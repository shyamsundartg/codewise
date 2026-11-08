"""Best-effort secret redaction before anything is embedded or sent to an LLM.

This is a safety net, not a guarantee: obvious secret files are skipped
entirely in ``source.py``; this catches keys hard-coded in source.
"""

import re

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),  # OpenAI-style keys
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),  # GitHub tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    # key = "long-random-looking-string"
    re.compile(
        r"""(?i)((?:api[_-]?key|secret|token|password)\s*[:=]\s*["'])[^"'\s]{12,}(["'])"""
    ),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(rf"\1{REDACTED}\2", text)
        else:
            text = pattern.sub(REDACTED, text)
    return text
