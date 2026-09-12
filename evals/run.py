"""Eval runner: run the suites, print a scorecard, gate on regression vs baseline.

    python -m evals.run                  # tool-search only (local, deterministic)
    python -m evals.run --routing        # + tool-routing (needs a local LLM)
    python -m evals.run --update-baseline # record current scores as the baseline

Exit code is non-zero if any suite regressed below ``baseline - tolerance``,
so the same command works as an on-demand gate.
"""

from __future__ import annotations

import argparse
import json
import sys

from evals._io import BASELINES
from evals.routing_eval import run_routing_eval
from evals.tool_search_eval import run_tool_search_eval

# Per-suite regression tolerance. Tool search is deterministic (tight); routing
# rides on a small LLM so it gets more slack.
#
# The retrieval suite is gone with the engine it measured: knowledge retrieval
# is now ripgrep over markdown files (ADR knowledge-is-plain-files), and scoring
# recall@k for ripgrep would measure ripgrep, not Coffer. What replaces it as a
# question — does an agent reading the catalogue open the right file? — needs a
# model, so it does not belong in the deterministic gate.
_TOLERANCE = {"routing": 0.10, "tool_search": 0.05}


def _baseline_path(suite: str):
    return BASELINES / f"{suite}.json"


def _load_baseline(suite: str) -> dict | None:
    path = _baseline_path(suite)
    return json.loads(path.read_text()) if path.exists() else None


def _save_baseline(report: dict) -> None:
    BASELINES.mkdir(exist_ok=True)
    suite = report["suite"]
    _baseline_path(suite).write_text(
        json.dumps(
            {"primary": report["primary"], "tolerance": _TOLERANCE.get(suite, 0.05)},
            indent=2,
        )
        + "\n"
    )


def _evaluate(report: dict, *, update: bool) -> bool:
    """Print one suite's result; return True if it passed the baseline gate."""
    suite, primary, n = report["suite"], report["primary"], report["n"]
    print(f"\n[{suite}] {primary['name']} = {primary['value']:.3f}  (n={n})")
    for key, val in report.get("secondary", {}).items():
        print(f"    {key}: {val}")

    if update:
        _save_baseline(report)
        print("    baseline updated.")
        return True

    baseline = _load_baseline(suite)
    if baseline is None:
        print("    no baseline yet — run with --update-baseline to record one.")
        return True
    floor = baseline["primary"]["value"] - baseline.get("tolerance", 0.05)
    if primary["value"] + 1e-9 < floor:
        print(
            f"    REGRESSION: {primary['value']:.3f} < {floor:.3f} (baseline "
            f"{baseline['primary']['value']:.3f} - tol {baseline.get('tolerance')})"
        )
        return False
    print(f"    OK vs baseline {baseline['primary']['value']:.3f} (floor {floor:.3f}).")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Coffer eval suites.")
    parser.add_argument(
        "--routing", action="store_true", help="also run the tool-routing suite"
    )
    parser.add_argument(
        "--update-baseline", action="store_true", help="record current as baseline"
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)

    reports: list[dict] = [run_tool_search_eval(top_k=args.top_k)]

    if args.routing:
        routing = run_routing_eval()
        if routing is None:
            print(
                "\n[routing] skipped — no local LLM reachable (set OLLAMA_URL/OLLAMA_MODEL)."
            )
        else:
            reports.append(routing)

    passed = all(_evaluate(r, update=args.update_baseline) for r in reports)
    print()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
