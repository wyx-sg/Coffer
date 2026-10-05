"""Find plaintext secrets in text (spec secret "Detect plaintext secrets with
the bundled rules").

One detector serves Find plaintext keys, the MCP server scan and vault sync's
check before a push. It applies each bundled gitleaks rule as gitleaks does —
keywords, pattern, secret group, entropy, path condition, the global and the
rule's allowlists — then Coffer's own allowlist and rules
(``coffer_rules``). A finding is a :class:`Detection`: the rule and where the
value is in the text, **never the value**.

Unlike gitleaks, a rule runs only in windows around its keywords: one long
line (an image pasted into a note as base64) would otherwise cost a
backtracking engine seconds per megabyte on some rules. A value two rules
find is one finding, named by the more specific rule.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from coffer.infrastructure.secret import coffer_rules
from coffer.infrastructure.secret.rule_set import Rule, RuleSet, bundled, shannon_entropy

#: Characters before a keyword hit a window starts, and after it a window ends.
WINDOW_BEFORE = 512
WINDOW_AFTER = 4096
#: A multi-line rule (a PEM block) reads this far past its keyword.
WINDOW_AFTER_MULTILINE = 65536
#: A text this short is read whole by every rule whose keyword it holds.
WHOLE_TEXT = 16384
#: Named last when two rules find one value: it is the catch-all.
GENERIC_RULE = "generic-api-key"


@dataclass(frozen=True, slots=True)
class Detection:
    """One plaintext value: ``text[start:end]``, never carried here."""

    rule: str
    start: int
    end: int
    #: The name the value is assigned to on its line, or ``""``.
    key: str = ""


class Lines:
    """Line numbers and line text for offsets of one text."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def number(self, offset: int) -> int:
        """The 1-based line ``offset`` is on."""
        return bisect.bisect_right(self._starts, offset)

    def start(self, number: int) -> int:
        return self._starts[number - 1]

    def line(self, number: int) -> str:
        begin = self._starts[number - 1]
        end = self._starts[number] - 1 if number < len(self._starts) else len(self.text)
        return self.text[begin:end]

    def segments(self, start: int, end: int) -> Iterator[tuple[int, int, int]]:
        """``(line, column start, column end)`` for each line ``[start, end)``
        covers — one for a value on one line, several for a PEM block."""
        n = self.number(start)
        while True:
            begin = self._starts[n - 1]
            line_end = begin + len(self.line(n))
            yield n, max(start, begin) - begin, min(end, line_end) - begin
            if end <= line_end or n >= len(self._starts):
                return
            n += 1


def _windows(low: str, rule: Rule) -> list[tuple[int, int]]:
    after = WINDOW_AFTER_MULTILINE if rule.multiline else WINDOW_AFTER
    spans: list[tuple[int, int]] = []
    for kw in rule.keywords:
        i = low.find(kw)
        while i != -1:
            spans.append((max(0, i - WINDOW_BEFORE), min(len(low), i + len(kw) + after)))
            i = low.find(kw, i + 1)
    spans.sort()
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _matches(rule: Rule, text: str, low: str) -> Iterator[re.Match[str]]:
    if rule.keywords and not any(kw in low for kw in rule.keywords):
        return
    if not rule.keywords or len(text) <= WHOLE_TEXT:
        yield from rule.regex.finditer(text)
        return
    seen: set[tuple[int, int]] = set()
    for s, e in _windows(low, rule):
        for m in rule.regex.finditer(text, s, e):
            # A match touching a cut window end may run on past it.
            if m.end() == e < len(text) or m.span() in seen:
                continue
            seen.add(m.span())
            yield m


def _priority(rule: str) -> int:
    if rule == GENERIC_RULE:
        return 2
    return 1 if rule.startswith("coffer-") else 0


def detect(text: str, path: str = "", rule_set: RuleSet | None = None) -> list[Detection]:
    """Every plaintext value in ``text``, in order. ``path`` (relative, ``/``
    separated) is what path conditions and path allowlists read; an empty
    path matches none of them."""
    rs = rule_set or bundled()
    if rs.allowlist.skips_path(path):
        return []
    low = text.lower()
    lines = Lines(text)
    found: list[tuple[int, int, Detection]] = []
    for order, rule in enumerate((*rs.rules, *coffer_rules.RULES)):
        if rule.path is not None and not (path and rule.path.search(path)):
            continue
        if any(a.skips_path(path) for a in rule.allowlists):
            continue
        for m in _matches(rule, text, low):
            start, end = rule.secret_span(m)
            secret = text[start:end]
            if not secret.strip("\n"):
                continue
            if rule.entropy and shannon_entropy(secret) <= rule.entropy:
                continue
            n = lines.number(start)
            line = lines.line(n)
            if any(
                a.allows(secret, m.group(0), line, path) for a in (rs.allowlist, *rule.allowlists)
            ):
                continue
            col = start - lines.start(n)
            col_end = min(len(line), col + (end - start))
            if coffer_rules.allows(line, col, col_end, code=_priority(rule.id) > 0):
                continue
            key = (
                coffer_rules.key_before(line, col)[0]
                or coffer_rules.key_before(line, max(0, m.start() - lines.start(n)))[0]
            )
            found.append((_priority(rule.id), order, Detection(rule.id, start, end, key)))
    kept: list[Detection] = []
    for _, _, d in sorted(found, key=lambda f: (f[0], f[1], f[2].start)):
        if not any(k.start < d.end and d.start < k.end for k in kept):
            kept.append(d)
    return sorted(kept, key=lambda d: (d.start, d.end))


def detect_setting(key: str, value: str) -> str | None:
    """The rule that says an MCP server's ``env`` or header value is a
    plaintext secret, or ``None``. The value is read as the line
    ``KEY: value``, so the bundled rules see its key; Coffer's server rule
    (``coffer_rules.setting_rule``) covers a secret-named key or a
    ``Bearer``/``Token`` credential."""
    line = f"{key}: {value}"
    offset = len(key) + 2
    for d in detect(line):
        if d.start >= offset:
            return d.rule
    return coffer_rules.setting_rule(key, value)


def by_line(text: str, detections: Sequence[Detection]) -> list[tuple[int, Detection]]:
    """``(line, detection)`` with the line each value starts on."""
    lines = Lines(text)
    return [(lines.number(d.start), d) for d in detections]


__all__ = [
    "GENERIC_RULE",
    "Detection",
    "Lines",
    "by_line",
    "detect",
    "detect_setting",
]
