"""Tiny dataset IO helpers for the eval suites."""

from __future__ import annotations

import json
from pathlib import Path

DATASETS = Path(__file__).resolve().parent / "datasets"
BASELINES = Path(__file__).resolve().parent / "baselines"


def load_jsonl(name: str) -> list[dict]:
    """Load ``datasets/<name>`` as a list of JSON objects (one per line)."""
    path = DATASETS / name
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_jsonl(name: str, rows: list[dict]) -> None:
    """Append JSON objects (one per line) to ``datasets/<name>``.

    Used by the curate CLI to grow a dataset from captured traces. Ensures the
    file ends in a newline before appending so lines never run together.
    """
    if not rows:
        return
    path = DATASETS / name
    needs_nl = (
        path.exists()
        and path.stat().st_size > 0
        and not path.read_text(encoding="utf-8").endswith("\n")
    )
    with path.open("a", encoding="utf-8") as fh:
        if needs_nl:
            fh.write("\n")
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
