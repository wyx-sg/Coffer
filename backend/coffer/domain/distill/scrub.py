"""Pure scrubbing of transcript text: redact secrets, drop oversized blobs.

Transcript content is fed to an LLM for distillation but is never persisted.
This module removes the obvious secrets and caps blob length before the text
leaves the machine in any form (e.g. as an LLM prompt).
"""

from __future__ import annotations

import re

_REDACTED = "[redacted]"
_TRUNCATED = " …[truncated]"

# Ordered list of (name, pattern) secret shapes. Patterns are deliberately
# conservative — they target well-known token formats so ordinary prose is
# left intact.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),  # OpenAI-style
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),  # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),  # AWS access key id
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b"),  # bearer tokens
    re.compile(r"\beyJ[A-Za-z0-9._-]{20,}\b"),  # JWTs
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"),  # password assignments
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),  # URL credentials user:pass@
    re.compile(r"(?i)\baws_secret_access_key\s*[=:]\s*\S+"),  # AWS secret key
)

_DEFAULT_MAX_CHARS = 2000


def scrub_text(text: str, *, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """Redact known secret shapes from ``text`` and truncate to ``max_chars``.

    Truncation appends a short marker; the result length never exceeds
    ``max_chars + len(" …[truncated]")``.
    """
    scrubbed = text
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub(_REDACTED, scrubbed)
    if len(scrubbed) > max_chars:
        scrubbed = scrubbed[:max_chars] + _TRUNCATED
    return scrubbed
