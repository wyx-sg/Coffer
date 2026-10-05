"""The port a secret's label and description are kept behind (spec secret
"Label and describe a secret without changing its reference")."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from coffer.domain.secrets import SecretNote


class SecretNotesPort(Protocol):
    def all(self) -> dict[str, SecretNote]: ...

    def get(self, ref: str) -> SecretNote | None: ...

    def put(self, ref: str, note: SecretNote | None, *, summary: str, actor: str | None) -> None:
        """Set ``ref``'s note; an empty or absent one removes the entry."""

    def update(
        self,
        ref: str,
        change: Callable[[SecretNote | None], SecretNote | None],
        *,
        summary: str,
        actor: str | None,
    ) -> SecretNote | None:
        """Read ``ref``'s note, apply ``change`` and write the result as one step:
        two saves at once (a label and a description, two dialogs) never
        overwrite each other or fail on the document having moved. Returns the
        note now stored."""
