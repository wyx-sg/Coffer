"""A resource's config between its file and the application (spec
vault-storage "Keep every vault document a JSON object that preserves what it
does not know").

Two translations happen at the store's edge:

- **Portability.** A string under this machine's home is written as
  ``${HOME}/...`` and expanded on read (``coffer.domain.vault.portability``),
  so the file never names one machine's home.
- **Keys this build does not know.** A newer build may have added a config
  key, or a person may have typed one. The application only ever sees the
  keys the kind's ``config_schema`` declares — the kinds validate with
  ``extra="forbid"``, so handing them an unknown key would turn a newer
  build's field into an error — and the store puts every other key back from
  the file, in its place, on every write. Only the config's **top-level**
  keys are compared: a schema's nested models are the kind's own business, and
  a key a newer build nests deeper is refused by that kind's validation like
  any other value it cannot read.

What a schema knows is ``coffer.domain.vault.config_keys.known_keys`` (a
channel's discriminated union reads the keys of the member it is); a schema
with ``extra="allow"`` knows every key, and a kind this build does not know
(``schema is None``) is passed through whole.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from coffer.domain.vault.config_keys import known_keys
from coffer.domain.vault.portability import expand_home, normalize_home


def _home() -> str:
    return str(Path(os.environ.get("HOME", "~")).expanduser())


def unknown_keys(config: Mapping[str, Any], schema: type[BaseModel] | None) -> list[str]:
    known = known_keys(schema, config)
    return [] if known is None else [k for k in config if k not in known]


def for_application(
    file_config: Mapping[str, Any], schema: type[BaseModel] | None
) -> dict[str, Any]:
    """The config a kind is handed: home expanded, unknown keys held back."""
    expanded = expand_home(file_config, _home())
    known = known_keys(schema, expanded)
    return expanded if known is None else {k: v for k, v in expanded.items() if k in known}


def for_file(
    config: Mapping[str, Any],
    file_config: Mapping[str, Any] | None,
    schema: type[BaseModel] | None,
) -> dict[str, Any]:
    """The config written to the file: ``config`` made portable, every key of
    the file's own config the schema does not know put back where it was."""
    portable = normalize_home(config, _home())
    known = known_keys(schema, portable)
    if not file_config or known is None:
        return portable
    out: dict[str, Any] = {}
    for key, value in file_config.items():
        if key in portable:
            out[key] = portable[key]
        elif key not in known:
            out[key] = value
    for key, value in portable.items():
        if key not in out:
            out[key] = value
    return out


__all__ = ["for_application", "for_file", "known_keys", "unknown_keys"]
