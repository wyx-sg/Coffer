"""The one validator every vault write passes through (spec vault-storage).

Each area of the vault registers the rule for its own files — resource
documents, a kind's state documents — under a path prefix.
A change is judged by the rule of the longest prefix that covers it; a path no
rule covers is accepted as it is (a knowledge document, a file inside a skill
folder: their bytes are the content). One composite is handed to the writer,
so the validator a person's edit meets is the validator a daemon write meets.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.vault.writes import Change, TreeReader, Validator, Verdict


class VaultValidator:
    """Dispatches each change to the rule registered for its prefix."""

    def __init__(self) -> None:
        self._rules: list[tuple[str, Validator]] = []

    def register(self, prefix: str, rule: Validator) -> None:
        """``rule`` judges every path under ``prefix`` (``"resources/"``)."""
        self._rules = sorted([*self._rules, (prefix, rule)], key=lambda r: -len(r[0]))

    def prefixes(self) -> tuple[str, ...]:
        return tuple(p for p, _ in self._rules)

    def __call__(self, changes: Sequence[Change], repo: TreeReader) -> Verdict:
        grouped: dict[int, list[Change]] = {}
        for change in changes:
            for index, (prefix, _rule) in enumerate(self._rules):
                if change.path.startswith(prefix):
                    grouped.setdefault(index, []).append(change)
                    break
        verdict = Verdict()
        for index, group in grouped.items():
            got = self._rules[index][1](group, repo)
            verdict.findings.extend(got.findings)
            verdict.fixes.extend(got.fixes)
        return verdict


__all__ = ["VaultValidator"]
