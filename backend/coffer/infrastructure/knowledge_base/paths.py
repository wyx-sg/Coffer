"""On-disk layout for the knowledge_base kind. Sole owner of path construction."""

from __future__ import annotations

import os
import pathlib


def kb_root() -> pathlib.Path:
    """Return `~/.coffer/kb/` (or `$COFFER_KB_ROOT` if set, for tests)."""
    override = os.environ.get("COFFER_KB_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "kb"


def kb_dir(kb_name: str) -> pathlib.Path:
    return kb_root() / kb_name


def kb_raw_dir(kb_name: str) -> pathlib.Path:
    return kb_dir(kb_name) / "raw"


def kb_index_dir(kb_name: str) -> pathlib.Path:
    return kb_dir(kb_name) / "index"


def raw_file_path(kb_name: str, document_id: str, extension: str) -> pathlib.Path:
    """Compute the raw-file path for ``<document_id><extension>``.

    Asserts the resolved path stays strictly under ``kb_raw_dir`` so a
    crafted ``extension`` (e.g. ``./../../etc/passwd``) cannot escape the KB
    sandbox (CODE22-006). The application-layer ``_extension`` already
    sanitises the extension, but this is the last line of defence — keep
    both.
    """
    raw_dir = kb_raw_dir(kb_name)
    candidate = raw_dir / f"{document_id}{extension}"
    resolved = candidate.resolve()
    raw_dir_resolved = raw_dir.resolve()
    try:
        resolved.relative_to(raw_dir_resolved)
    except ValueError as exc:
        raise ValueError(
            "refusing to write raw file outside kb_raw_dir: "
            f"{resolved} not under {raw_dir_resolved}"
        ) from exc
    return candidate
