#!/usr/bin/env python3
"""Refresh the bundled model price list from pydantic/genai-prices.

Run at release time (``make refresh-prices``): the file this writes ships in
every build. Between releases the daemon refreshes a cached copy of the same
published file once a day (spec provider-switching "Refresh the bundled price
list in the background"); this keeps the shipped snapshot current.

What it does:

1. resolves the head commit of ``pydantic/genai-prices``'s default branch;
2. downloads ``prices/new_data/v2/data.json`` (the file genai-prices' own
   ``UpdatePrices`` fetches) and ``LICENSE`` at that commit;
3. keeps only what pricing reads — each provider's id, name, ``api_pattern``,
   ``model_match``, ``provider_match`` and ``fallback_model_providers``, and
   each model's id, ``match``, ``prices`` and ``context_window`` — so the file
   shipped in every build stays small;
4. writes ``backend/coffer/infrastructure/usage/price_list/genai-prices.json`` with
   the commit and date it came from, and the licence beside it (MIT: the
   notice travels with the data).

Usage::

    python scripts/refresh_model_prices.py            # write the files
    python scripts/refresh_model_prices.py --check    # exit 1 if they would change
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO = "pydantic/genai-prices"
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "coffer" / "infrastructure" / "usage" / "price_list"
DATA_FILE = DATA_DIR / "genai-prices.json"
LICENSE_FILE = DATA_DIR / "genai-prices.LICENSE"

_PROVIDER_KEYS = (
    "id",
    "name",
    "api_pattern",
    "model_match",
    "provider_match",
    "fallback_model_providers",
)
_MODEL_KEYS = ("id", "match", "prices", "context_window")


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "coffer-release"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def _head_commit() -> str:
    data = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/main"))
    return str(data["sha"])


def slim(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only the fields pricing reads, in a stable order."""
    out: list[dict[str, Any]] = []
    for provider in providers:
        kept = {k: provider[k] for k in _PROVIDER_KEYS if provider.get(k) is not None}
        kept["models"] = [
            {k: model[k] for k in _MODEL_KEYS if model.get(k) is not None}
            for model in provider.get("models", [])
        ]
        out.append(kept)
    return out


def build(commit: str, today: str) -> tuple[str, str]:
    raw = json.loads(_get(f"https://raw.githubusercontent.com/{REPO}/{commit}/prices/new_data/v2/data.json"))
    licence = _get(f"https://raw.githubusercontent.com/{REPO}/{commit}/LICENSE").decode("utf-8")
    document = {
        "source": f"https://github.com/{REPO}",
        "commit": commit,
        "fetched": today,
        "license": "MIT",
        "providers": slim(raw),
    }
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=False) + "\n", licence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = parser.parse_args(argv)
    commit = _head_commit()
    current = json.loads(DATA_FILE.read_text("utf-8")) if DATA_FILE.exists() else {}
    if args.check:
        if current.get("commit") == commit:
            print(f"bundled prices are at {commit[:12]} (current)")
            return 0
        print(f"bundled prices are at {str(current.get('commit'))[:12]}; upstream is {commit[:12]}")
        return 1
    data, licence = build(commit, _dt.date.today().isoformat())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(data, "utf-8")
    LICENSE_FILE.write_text(licence, "utf-8")
    print(f"wrote {DATA_FILE.relative_to(ROOT)} from {REPO}@{commit[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
