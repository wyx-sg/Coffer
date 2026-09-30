"""A resource's config between its file and the application: portability
(spec vault-storage "Keep every vault document a JSON object that preserves
what it does not know").

A string under this machine's home is written as ``${HOME}/...`` and expanded
on read (``coffer.domain.vault.portability``), so the file never names one
machine's home.

Nothing else is translated. A config key the kind's ``config_schema`` does not
declare never reaches ``HEAD``: the vault's resource rule refuses the file
(``application.vault.resource_rules``), as the kinds' own models do
(``extra="forbid"``), so the store neither filters nor puts back keys.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from coffer.domain.vault.portability import expand_home, normalize_home


def _home() -> str:
    return str(Path(os.environ.get("HOME", "~")).expanduser())


def for_application(file_config: Mapping[str, Any]) -> dict[str, Any]:
    """The config a kind is handed: this machine's home expanded."""
    return dict(expand_home(file_config, _home()))


def for_file(config: Mapping[str, Any]) -> dict[str, Any]:
    """The config written to the file: this machine's home made portable."""
    return dict(normalize_home(config, _home()))


__all__ = ["for_application", "for_file"]
