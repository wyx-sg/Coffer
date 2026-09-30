"""Read the model proxy's usage spool (``~/.coffer/proxy-usage/``).

The proxy appends records to ``*.jsonl.part`` files and renames each to
``*.jsonl`` once it will not grow again (:mod:`coffer.domain.usage.records`).
This reader lists only completed files — a ``.part`` file is never opened — and
parses them line by line into :class:`UsageRecord`; a line that is not JSON or
does not validate is counted as malformed and skipped, so one bad line never
holds back the rest of its file. Deleting is the ingest's call, made only after
the file's rows are committed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from coffer.application.usage.ports import SpoolBatch
from coffer.domain.usage.records import (
    SPOOL_DIR_ENV,
    SPOOL_SUFFIX,
    UsageRecord,
)
from coffer.infrastructure.vault.home import proxy_usage_dir


def default_spool_dir() -> Path:
    """``$COFFER_PROXY_SPOOL_DIR``, else ``~/.coffer/proxy-usage``."""
    override = os.environ.get(SPOOL_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return proxy_usage_dir()


class FileSpoolReader:
    """``SpoolReader`` over one spool directory."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory if directory is not None else default_spool_dir()

    @property
    def directory(self) -> Path:
        return self._dir

    def completed(self) -> list[Path]:
        """Completed spool files, oldest name first (names sort by time)."""
        try:
            entries = list(self._dir.iterdir())
        except FileNotFoundError:
            return []
        # ``x.jsonl.part`` ends in ".part", so the suffix test alone excludes it.
        return sorted(p for p in entries if p.is_file() and p.name.endswith(SPOOL_SUFFIX))

    def read(self, path: Path) -> SpoolBatch:
        records: list[UsageRecord] = []
        malformed = 0
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                text = line.strip()
                if not text:
                    continue
                try:
                    records.append(UsageRecord.model_validate(json.loads(text)))
                except (ValueError, ValidationError):
                    malformed += 1
        return SpoolBatch(records=records, malformed=malformed)

    def delete(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return


__all__ = ["FileSpoolReader", "default_spool_dir"]
