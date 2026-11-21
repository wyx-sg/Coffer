"""The proxy token files of agents that read their key from a file (ADR
opencode-reads-its-proxy-token-from-a-file).

OpenCode runs no command for a provider key; its ``opencode.json`` names a
file instead (``{file:…}``). Coffer keeps that file, one per agent, under
``~/.coffer/local/proxy-tokens/<agent name>``: the directory is ``0700``, the
file ``0600`` and replaced atomically, so OpenCode never reads half a token.
The secret store stays the token's record; the file is a copy Coffer rewrites
whenever the token is issued or rotated and deletes when the agent goes.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import tempfile


class TokenFileMirror:
    """Writes and removes ``<dir>/<agent name>``."""

    def __init__(self, directory: pathlib.Path) -> None:
        self._dir = directory

    def path_for(self, agent: str) -> pathlib.Path:
        return self._dir / agent

    def write(self, agent: str, token: str) -> None:
        """Make the file hold exactly ``token``; a file that already does is
        left alone, so a state push rewrites nothing."""
        path = self.path_for(agent)
        try:
            if path.read_text(encoding="utf-8") == token:
                return
        except OSError:
            pass
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, 0o700)
        fd, tmp = tempfile.mkstemp(dir=self._dir, prefix=f".{agent}.")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(token)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def remove(self, agent: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path_for(agent).unlink()


__all__ = ["TokenFileMirror"]
