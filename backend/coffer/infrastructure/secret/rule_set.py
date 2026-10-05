"""The bundled plaintext-secret rules, loaded once
(spec secret "Detect plaintext secrets with the bundled rules").

``rules/gitleaks.toml`` is gitleaks' default rule set at a pinned release,
its patterns already translated to Python ``re`` by
``scripts/sync_gitleaks_rules.py``. This module reads it into compiled rules
and allowlists; ``detector`` applies them.

Every pattern is compiled with ``re.ASCII``: RE2's ``\\w``, ``\\d``, ``\\s``
and ``\\b`` are ASCII.
"""

from __future__ import annotations

import functools
import math
import pathlib
import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

RULES_FILE = pathlib.Path(__file__).with_name("rules") / "gitleaks.toml"


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.ASCII)


def shannon_entropy(value: str) -> float:
    """Bits per character, as gitleaks computes it."""
    if not value:
        return 0.0
    n = len(value)
    return -sum(c / n * math.log2(c / n) for c in Counter(value).values())


@dataclass(frozen=True)
class Allowlist:
    """What a rule (or every rule) does not report.

    ``target`` says what ``regexes`` are matched against: the ``secret``
    (default), the whole ``match`` or the ``line``. ``stopwords`` are matched,
    lowercased, inside the secret. With ``condition == "AND"`` every
    configured check must hold; otherwise any regex or stopword does, and
    ``paths`` skip the file before it is read."""

    regexes: tuple[re.Pattern[str], ...] = ()
    paths: tuple[re.Pattern[str], ...] = ()
    stopwords: tuple[str, ...] = ()
    target: str = "secret"
    condition: str = "OR"

    @classmethod
    def from_toml(cls, raw: dict[str, Any]) -> Allowlist:
        return cls(
            regexes=tuple(_compile(p) for p in raw.get("regexes", ())),
            paths=tuple(_compile(p) for p in raw.get("paths", ())),
            stopwords=tuple(w.lower() for w in raw.get("stopwords", ())),
            target=raw.get("regexTarget", "secret"),
            condition=str(raw.get("condition", "OR")).upper(),
        )

    def skips_path(self, path: str) -> bool:
        """Whether ``path`` is not read at all (an ``OR`` list's paths)."""
        return self.condition != "AND" and bool(path) and any(p.search(path) for p in self.paths)

    def allows(self, secret: str, match: str, line: str, path: str) -> bool:
        target = {"match": match, "line": line}.get(self.target, secret)
        by_regex = bool(target) and any(p.search(target) for p in self.regexes)
        lowered = secret.lower()
        by_word = any(w in lowered for w in self.stopwords)
        if self.condition != "AND":
            return by_regex or by_word
        checks: list[bool] = []
        if self.paths:
            checks.append(bool(path) and any(p.search(path) for p in self.paths))
        if self.regexes:
            checks.append(by_regex)
        if self.stopwords:
            checks.append(by_word)
        return bool(checks) and all(checks)


@dataclass(frozen=True)
class Rule:
    id: str
    regex: re.Pattern[str]
    #: Lowercased; the rule runs only where one of them appears.
    keywords: tuple[str, ...] = ()
    #: 0: the first non-empty group, else the whole match.
    secret_group: int = 0
    #: A secret at or below this many bits per character is not reported.
    entropy: float = 0.0
    path: re.Pattern[str] | None = None
    allowlists: tuple[Allowlist, ...] = ()
    #: Whether a match can run across many lines (a PEM block).
    multiline: bool = False

    @classmethod
    def from_toml(cls, raw: dict[str, Any]) -> Rule:
        return cls(
            id=raw["id"],
            regex=_compile(raw["regex"]),
            keywords=tuple(k.lower() for k in raw.get("keywords", ())),
            secret_group=int(raw.get("secretGroup", 0)),
            entropy=float(raw.get("entropy") or 0.0),
            path=_compile(raw["path"]) if raw.get("path") else None,
            allowlists=tuple(Allowlist.from_toml(a) for a in raw.get("allowlists", ())),
            multiline="[\\s\\S" in raw["regex"] or "(?s" in raw["regex"],
        )

    def secret_span(self, m: re.Match[str]) -> tuple[int, int]:
        """Where the secret is in the text: the configured group, else the
        first non-empty group, else the whole match."""
        groups = m.re.groups
        if groups and self.secret_group and self.secret_group <= groups:
            return m.span(self.secret_group)
        for g in range(1, groups + 1):
            if m.group(g):
                return m.span(g)
        return m.span()


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
    allowlist: Allowlist
    #: ``[source]`` of the rule file: repository, version, commit, licence.
    source: dict[str, Any] = field(default_factory=dict)


def parse(document: dict[str, Any]) -> RuleSet:
    """A rule set from a parsed rule file. A rule with no pattern (gitleaks'
    path-only rules, which name a file by its name alone) is not a content
    rule and is left out."""
    rules = tuple(Rule.from_toml(r) for r in document.get("rules", ()) if r.get("regex"))
    return RuleSet(
        rules=rules,
        allowlist=Allowlist.from_toml(document.get("allowlist") or {}),
        source=dict(document.get("source") or {}),
    )


@functools.cache
def bundled() -> RuleSet:
    """The rule set Coffer ships, compiled once per process."""
    with RULES_FILE.open("rb") as f:
        return parse(tomllib.load(f))


__all__ = ["RULES_FILE", "Allowlist", "Rule", "RuleSet", "bundled", "parse", "shannon_entropy"]
