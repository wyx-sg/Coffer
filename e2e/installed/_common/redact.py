"""Keep the daemon token and every canary out of what a run writes."""

from __future__ import annotations

import json
from typing import Any

MASK = "[REDACTED]"


class Redactor:
    """Replaces each registered value wherever it appears in text or JSON."""

    def __init__(self) -> None:
        self._values: set[str] = set()

    def add(self, value: str | None) -> None:
        # Short values would mask ordinary words; nothing this suite hides is short.
        if value and len(value) >= 8:
            self._values.add(value)

    def text(self, text: str) -> str:
        for value in sorted(self._values, key=len, reverse=True):
            text = text.replace(value, MASK)
        return text

    def value(self, value: Any) -> Any:
        """A JSON-safe copy of ``value`` with every registered value masked."""
        return json.loads(self.text(json.dumps(value, default=str)))

    def contains_secret(self, text: str) -> bool:
        return any(value in text for value in self._values)
