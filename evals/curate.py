"""Curate captured traces into golden eval cases (ADR-019, slice 3).

The curate hop of the eval flywheel: ``capture -> [curate] -> dataset -> gate``.
It reads the opt-in capture sink (JSONL written when ``COFFER_EVAL_CAPTURE`` is
set), drops queries already covered by the dataset, asks which returned tools
were actually relevant, and appends the confirmed cases to
``datasets/tool_search.jsonl``.

The terminal interaction is a thin shell over pure functions (``load_captures``,
``parse_selection``, ``build_case``, ``curate``); the driver takes an injected
``labeler`` so the whole flow is testable without a TTY.

    python -m evals.curate                 # label captures from the default sink
    python -m evals.curate --input cap.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path

from evals._io import DATASETS, append_jsonl, load_jsonl

#: A labeler is shown one capture record and returns the relevant tool names,
#: ``[]`` (seen, nothing relevant), or ``None`` (skip / undecided).
Labeler = Callable[[dict], "list[str] | None"]

_KIND = "tool_search"
_DEFAULT_SINK = Path("~/.coffer/eval-capture.jsonl")


def _norm(query: str) -> str:
    """Collapse whitespace so trivially-different queries dedup together."""
    return " ".join(query.split())


def load_captures(path: Path) -> list[dict]:
    """Load valid ``tool_search`` capture records from a JSONL sink.

    Malformed lines, blank lines, other kinds, and records missing a query or
    results are skipped rather than fatal — the sink is an append-only dev log.
    """
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(rec, dict)
            and rec.get("kind") == _KIND
            and isinstance(rec.get("query"), str)
            and rec["query"].strip()
            and isinstance(rec.get("results"), list)
            and rec["results"]
        ):
            rows.append(rec)
    return rows


def parse_selection(raw: str, results: list[str]) -> list[str] | None:
    """Map a user's selection over ``results`` to chosen tool names.

    - ``skip`` -> ``None`` (undecided; present again another time)
    - ``all`` -> every result
    - ``none`` / blank -> ``[]`` (seen, nothing relevant)
    - ``"1,3"`` -> the 1-based picks, de-duped, in result order; out-of-range
      indices are ignored.
    """
    token = raw.strip().lower()
    if token == "skip":
        return None
    if token == "all":
        return list(results)
    if token in ("", "none"):
        return []
    picked: set[int] = set()
    for part in token.replace(" ", ",").split(","):
        if not part:
            continue
        try:
            idx = int(part)
        except ValueError:
            continue
        if 1 <= idx <= len(results):
            picked.add(idx - 1)
    return [results[i] for i in sorted(picked)]


def build_case(query: str, expected: list[str]) -> dict:
    """Shape one golden ``tool_search`` case, tagged with its provenance."""
    return {"query": query, "expected": list(expected), "source": "captured"}


def curate(
    captures: Iterable[dict],
    seen_queries: set[str],
    labeler: Labeler,
) -> list[dict]:
    """Drive labeling: dedup vs the dataset + within the batch, then label.

    A capture is presented to ``labeler`` only if its (whitespace-normalised)
    query is new. A non-empty label becomes a case; ``None`` or ``[]`` is
    dropped (skipped / nothing relevant).
    """
    seen = {_norm(q) for q in seen_queries}
    cases: list[dict] = []
    for rec in captures:
        key = _norm(rec["query"])
        if key in seen:
            continue
        seen.add(key)  # collapse in-batch duplicates too
        chosen = labeler(rec)
        if chosen:
            cases.append(build_case(rec["query"], chosen))
    return cases


# --------------------------------------------------------------------------- #
# Interactive shell                                                           #
# --------------------------------------------------------------------------- #


def _interactive_labeler(record: dict) -> list[str] | None:
    results = record["results"]
    print(f"\nquery: {record['query']!r}")
    for i, name in enumerate(results, 1):
        print(f"  {i}. {name}")
    try:
        raw = input("relevant tool(s) [e.g. 1,2 / all / none / skip]: ")
    except (EOFError, KeyboardInterrupt):
        return None  # Ctrl-D / Ctrl-C ends the record cleanly, no traceback
    return parse_selection(raw, results)


def _resolve_sink(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("COFFER_EVAL_CAPTURE", "").strip()
    if env and env.lower() not in ("1", "true", "yes", "0", "false", "no"):
        return Path(env).expanduser()
    return _DEFAULT_SINK.expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Curate captured traces into eval cases."
    )
    parser.add_argument(
        "--input", help="capture JSONL sink (default: COFFER_EVAL_CAPTURE / ~/.coffer)"
    )
    parser.add_argument(
        "--dataset", default="tool_search.jsonl", help="dataset file to grow"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show cases without writing"
    )
    args = parser.parse_args(argv)

    sink = _resolve_sink(args.input)
    captures = load_captures(sink)
    if not captures:
        print(f"no capturable tool_search records in {sink}")
        return 0

    seen = {row["query"] for row in load_jsonl(args.dataset)}
    cases = curate(captures, seen, _interactive_labeler)

    if not cases:
        print("\nno new cases.")
        return 0
    if args.dry_run:
        print(
            f"\n[dry-run] would append {len(cases)} case(s) to datasets/{args.dataset}:"
        )
        for c in cases:
            print(f"  {json.dumps(c)}")
        return 0

    append_jsonl(args.dataset, cases)
    print(f"\nappended {len(cases)} case(s) to {DATASETS / args.dataset}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
