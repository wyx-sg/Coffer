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
