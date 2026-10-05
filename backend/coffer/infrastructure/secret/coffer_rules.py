"""Coffer's own allowlist and rules, on top of the bundled gitleaks rules
(spec secret "Detect plaintext secrets with the bundled rules").

The imported rule file is never edited; what Coffer adds lives here.

**Not reported** (``allows``): a secret reference — ``coffer://secret/<id>``,
or the bare ``secret/<id>`` a resource document's ``secret_refs`` holds, which
``generic-api-key`` would otherwise flag in every MCP server's document — an
interpolation (``$VAR``, ``${VAR}``, ``{{…}}``), a placeholder, code that names
a value rather than holding one, and anything on a ``coffer run`` line (its
``--secret ENV=NAME`` names a secret).

**Also reported** (``RULES``): what gitleaks leaves out on purpose and a person
still means as a secret — a value assigned to a password-named key whatever
its entropy (``generic-api-key`` wants ten characters and more than 3.5 bits
per character), and a password inside a URL. ``setting_rule`` is the MCP
server rule: a server's ``env`` and header keys are config, not prose, so a
secret-sounding key alone says its value is a secret.
"""

from __future__ import annotations

import re

from coffer.domain.plaintext_shape import is_reference
from coffer.infrastructure.secret.rule_set import Allowlist, Rule

PASSWORD_RULE = "coffer-password-assignment"
URL_RULE = "coffer-url-password"
SETTING_RULE = "coffer-server-setting"

#: ``coffer://secret/<name>`` (any name a person gave it) and the bare
#: ``secret/<32 hex>`` ref a resource cites.
_REFERENCE = re.compile(r"coffer://secret/[A-Za-z0-9_.\-/]+|\bsecret/[0-9a-f]{32}\b")
_INTERPOLATION = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\{\{.*?\}\}")
PLACEHOLDER = re.compile(
    r"(?i)^(x{3,}|\*{3,}|\.{3,}|<.*>|your[-_].*|changeme|example.*|placeholder.*"
    r"|dummy.*|redacted|replace[-_]?me.*)$"
)
#: An unquoted value holding call, index or list punctuation is code
#: (``token = m.group(0)``, ``password=password,``), never a literal secret.
_CODE = re.compile(r"[()\[\],;]")
#: One bare name: in a declaration (``const token = apiToken``) or a member
#: assignment (``self.password = password_hash``) it is a variable, not a value.
_NAME = re.compile(r"^[A-Za-z_$][\w$]*$")
_DECLARED = re.compile(r"\b(?:const|let|var|final|val|auto)\s+[A-Za-z_$][\w$]*\s*[:=]\s*$")
_MEMBER = re.compile(r"\b(?:self|this|cls)\.[\w.]+\s*[:=]\s*$")
#: The name a value is assigned to, read back from the text before it on its line.
_KEY_BEFORE = re.compile(
    r"""(?<![\w/:.$-])(?P<key>[A-Za-z_$][\w.$-]*)["']?[ \t]*"""
    r"""(?::=|=>|\?=|[:=])[ \t]*(?P<q>[`'"]?)[ \t]*$"""
)

_IDENTIFIER = Allowlist(regexes=(re.compile(r"^[a-z_]+$|^[A-Z_]+$"),))
_URL_WORD = Allowlist(
    regexes=(re.compile(r"(?i)^(?:pass|password|passwd|pwd|secret|pass(?:word)?\d?)$"),)
)

RULES: tuple[Rule, ...] = (
    Rule(
        id=PASSWORD_RULE,
        regex=re.compile(
            r"(?i)[\w.-]*(?:password|passwd|pwd|passphrase)[\w.-]*[\"']?[ \t]*(?::=|=|:)[ \t]*"
            r"([\"'`]?)([^\s\"'`#]{8,})\1",
            re.ASCII,
        ),
        keywords=("password", "passwd", "pwd", "passphrase"),
        secret_group=2,
        allowlists=(_IDENTIFIER,),
    ),
    Rule(
        id=URL_RULE,
        regex=re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s:/@]{3,})@[\w.-]+", re.ASCII),
        keywords=("://",),
        allowlists=(_URL_WORD,),
    ),
)

_SETTING_KEY = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key"
    r"|authorization|auth)"
)
_CREDENTIAL = re.compile(r"^(Bearer|Token)\s+\S")
_MIN_SETTING = 8


def key_before(line: str, col: int) -> tuple[str, str]:
    """The name assigned the value starting at ``col`` of ``line``, and the
    quote that opens it (``""`` when unquoted); ``("", "")`` when the value
    is not assigned to a name."""
    m = _KEY_BEFORE.search(line[:col])
    return (m.group("key"), m.group("q")) if m else ("", "")


def _is_code(line: str, start: int, value: str, key: str, quoted: bool) -> bool:
    """Whether an unquoted assigned value names a value instead of holding
    one: call, index or list punctuation, a dotted reference such as an
    environment-variable read (``process.env.SPACE_TOKEN``), or a bare name a
    declaration or a member assignment gives."""
    if quoted:
        return False
    if is_reference(value) or (key and _CODE.search(value)):
        return True
    before = line[:start]
    return bool(_NAME.match(value)) and bool(_DECLARED.search(before) or _MEMBER.search(before))


def allows(line: str, start: int, end: int) -> bool:
    """Whether the value at ``line[start:end]`` is something Coffer never
    reports, whichever rule found it."""
    value = line[start:end]
    if "coffer run" in line:
        return True
    for pattern in (_REFERENCE, _INTERPOLATION):
        if any(m.start() < end and start < m.end() for m in pattern.finditer(line)):
            return True
    stripped = value.strip()
    if not stripped or stripped.startswith(("$", "{{")) or PLACEHOLDER.match(stripped):
        return True
    key, quote = key_before(line, start)
    quoted = bool(quote) and line[end : end + 1] == quote
    return _is_code(line, start, value, key, quoted)


def setting_rule(key: str, value: str) -> str | None:
    """``SETTING_RULE`` when an MCP server's ``env`` or header value is a
    plaintext secret by its key or its ``Bearer``/``Token`` form, else ``None``."""
    v = value.strip()
    if len(v) < _MIN_SETTING or allows(f"{key}: {v}", len(key) + 2, len(key) + 2 + len(v)):
        return None
    return SETTING_RULE if _SETTING_KEY.search(key) or _CREDENTIAL.match(v) else None


__all__ = [
    "PASSWORD_RULE",
    "PLACEHOLDER",
    "RULES",
    "SETTING_RULE",
    "URL_RULE",
    "allows",
    "key_before",
    "setting_rule",
]
