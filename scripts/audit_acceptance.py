#!/usr/bin/env python3
"""Audit acceptance-scenario coverage across spec.md files and test markers.

Convention (see agents/testing.md "Acceptance Scenarios — Cross-Tier Markers"):
  * Spec scenarios live in `specs/<id>/spec.md` under '## Acceptance Scenarios'
    as `### <title>` (or `### Scenario: <title>`) headings.
  * Spec ID is the spec's directory name (e.g. specs/001-mcp-servers/spec.md
    → '001-mcp-servers').
  * Python tests carry `@pytest.mark.acceptance(spec="...", scenario="...")`.
  * TS tests use `test.acceptance("spec", "scenario", ...)`.

Exits non-zero on:
  * any scenario in spec.md without a matching marker (missing coverage)
  * any marker referring to a scenario / spec id that doesn't exist (orphan)

Stdlib-only; no install required.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "specs"
BACKEND_TESTS = REPO_ROOT / "backend" / "tests"
FRONTEND_TS_ROOTS = [
    REPO_ROOT / "frontend" / "src",
    REPO_ROOT / "frontend" / "tests",
    REPO_ROOT / "e2e",
]
TS_SKIP_DIRS = {"node_modules", "dist", "build", ".next", "test-results"}

ACCEPTANCE_HEADER_RE = re.compile(r"^##\s+Acceptance\s+Scenarios\s*$", re.IGNORECASE)
NEXT_H2_RE = re.compile(r"^##\s+(?!Acceptance\s+Scenarios)", re.IGNORECASE)
SCENARIO_HEADING_RE = re.compile(r"^###\s+(?:Scenario:\s*)?(.+?)\s*$", re.IGNORECASE)
# Matches the standalone acceptance helper exported from
# frontend/src/test/acceptance.ts. See agents/testing.md.
#
# The lookbehind (?<![.\w]) ensures we don't false-match method calls or
# identifiers — only the bare acceptance() call counts.
#
# Each string argument is matched as one of two alternatives — a
# double-quoted run or a single-quoted run — so the closing delimiter must
# match the opening one. The excluded-char class inside each alternative
# only excludes ITS OWN delimiter, so a scenario title containing an
# apostrophe (e.g. "the fleet view renders any machine's activation slice")
# parses fully when the call uses double quotes, instead of truncating at
# the apostrophe as a naive "either quote" class would.
TS_ACCEPTANCE_RE = re.compile(
    r"(?<![.\w])acceptance\s*\(\s*"
    r"(?:\"(?P<spec_dq>[^\"]+)\"|'(?P<spec_sq>[^']+)')"
    r"\s*,\s*"
    r"(?:\"(?P<scenario_dq>[^\"]+)\"|'(?P<scenario_sq>[^']+)')"
)

# Strip JS/TS comments before regex matching. Without this, a quoted
# example inside a // or /* */ comment would be miscounted as a real
# test marker. Approximate (doesn't track string-vs-comment state across
# lines), but good enough for an audit-only pass — markers in real code
# always live in plain top-level statements.
TS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
TS_LINE_COMMENT_RE = re.compile(r"//[^\n]*")


def _strip_ts_comments(text: str) -> str:
    text = TS_BLOCK_COMMENT_RE.sub("", text)
    text = TS_LINE_COMMENT_RE.sub("", text)
    return text


def parse_spec_scenarios(spec_md: Path) -> list[str]:
    scenarios: list[str] = []
    in_section = False
    for line in spec_md.read_text(encoding="utf-8").splitlines():
        if ACCEPTANCE_HEADER_RE.match(line):
            in_section = True
            continue
        if in_section and NEXT_H2_RE.match(line):
            break
        if in_section:
            m = SCENARIO_HEADING_RE.match(line)
            if m:
                scenarios.append(m.group(1).strip())
    return scenarios


def collect_specs() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    if not SPECS_DIR.exists():
        return out
    for spec_md in sorted(SPECS_DIR.glob("*/spec.md")):
        out[spec_md.parent.name] = set(parse_spec_scenarios(spec_md))
    return out


def _extract_acceptance_call(node: ast.Call) -> tuple[str, str] | None:
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "acceptance"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "mark"
    ):
        return None
    spec: object = None
    scenario: object = None
    for kw in node.keywords:
        if kw.arg == "spec" and isinstance(kw.value, ast.Constant):
            spec = kw.value.value
        elif kw.arg == "scenario" and isinstance(kw.value, ast.Constant):
            scenario = kw.value.value
    if spec is None and node.args and isinstance(node.args[0], ast.Constant):
        spec = node.args[0].value
    if (
        scenario is None
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    ):
        scenario = node.args[1].value
    if isinstance(spec, str) and isinstance(scenario, str):
        return (spec, scenario)
    return None


def _is_unconditional_skip(dec: ast.expr) -> bool:
    """True for ``@pytest.mark.skip`` / ``@pytest.mark.skip(...)`` — NOT skipif.

    A bare ``skip`` marker hides the test from every run, so an acceptance
    marker sitting on it reports green while the scenario is never executed.
    ``skipif`` is conditional (the test may run under the right env) and is
    intentionally allowed.
    """
    target = dec.func if isinstance(dec, ast.Call) else dec
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "skip"
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "mark"
    )


def _module_pytestmark_skips(tree: ast.Module) -> bool:
    """True when a module-level ``pytestmark`` unconditionally skips the file.

    Covers ``pytestmark = pytest.mark.skip(...)`` and
    ``pytestmark = [pytest.mark.skip(...), ...]``.
    """
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets
        ):
            continue
        values = (
            stmt.value.elts
            if isinstance(stmt.value, ast.List | ast.Tuple)
            else [stmt.value]
        )
        if any(_is_unconditional_skip(v) for v in values):
            return True
    return False


def _scan_python_file(
    py: Path,
    tree: ast.Module,
    markers: set[tuple[str, str]],
    dead: list[tuple[str, str, str]],
) -> None:
    """One AST pass: collect acceptance markers AND dead (always-skipped) ones.

    A marker is dead when its test can never run: a ``@pytest.mark.skip`` on
    the function itself, on an enclosing class, or a module-level
    ``pytestmark`` skip — any of those would report the scenario covered
    while it never executes.
    """
    module_skipped = _module_pytestmark_skips(tree)

    def visit(node: ast.AST, scope_skipped: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                cls_skipped = scope_skipped or any(
                    _is_unconditional_skip(d) for d in child.decorator_list
                )
                visit(child, cls_skipped)
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                # A test may stack several acceptance decorators (one per
                # scenario it covers) — record every one, not just the last.
                pairs: list[tuple[str, str]] = []
                fn_skipped = scope_skipped
                for dec in child.decorator_list:
                    if isinstance(dec, ast.Call):
                        found = _extract_acceptance_call(dec)
                        if found is not None:
                            pairs.append(found)
                    if _is_unconditional_skip(dec):
                        fn_skipped = True
                for pair in pairs:
                    markers.add(pair)
                    if fn_skipped:
                        dead.append(
                            (
                                pair[0],
                                pair[1],
                                f"{py.relative_to(REPO_ROOT)}::{child.name}",
                            )
                        )
                visit(child, fn_skipped)
            else:
                visit(child, scope_skipped)

    visit(tree, module_skipped)


def collect_python_markers_and_dead(
    root: Path,
) -> tuple[set[tuple[str, str]], list[tuple[str, str, str]]]:
    """Single sweep over the test tree → (all markers, dead markers)."""
    markers: set[tuple[str, str]] = set()
    dead: list[tuple[str, str, str]] = []
    if not root.exists():
        return markers, dead
    for py in root.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        _scan_python_file(py, tree, markers, dead)
    return markers, dead


def collect_ts_markers(roots: list[Path]) -> set[tuple[str, str]]:
    markers: set[tuple[str, str]] = set()
    for root in roots:
        if not root.exists():
            continue
        for ext in ("*.ts", "*.tsx"):
            for src in root.rglob(ext):
                if any(part in TS_SKIP_DIRS for part in src.parts):
                    continue
                try:
                    text = src.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                stripped = _strip_ts_comments(text)
                for m in TS_ACCEPTANCE_RE.finditer(stripped):
                    spec = (
                        m.group("spec_dq")
                        if m.group("spec_dq") is not None
                        else m.group("spec_sq")
                    )
                    scenario = (
                        m.group("scenario_dq")
                        if m.group("scenario_dq") is not None
                        else m.group("scenario_sq")
                    )
                    markers.add((spec, scenario))
    return markers


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit acceptance scenario coverage.")
    parser.add_argument("--quiet", action="store_true", help="suppress success output")
    args = parser.parse_args()

    specs = collect_specs()
    if not specs:
        if not args.quiet:
            print("audit_acceptance: no specs/<id>/spec.md found — nothing to audit.")
        return 0

    # A spec.md with zero scenarios is almost certainly a malformed spec
    # (missing the `## Acceptance Scenarios` section, or all `###` subsections
    # deleted). Without this guard the audit silently passes as "0 missing
    # coverage", giving false confidence.
    empty_specs = sorted(
        spec_id for spec_id, scenarios in specs.items() if not scenarios
    )
    if empty_specs:
        print(
            "audit_acceptance: FAIL — spec.md(s) with no acceptance scenarios:",
            file=sys.stderr,
        )
        for spec_id in empty_specs:
            print(
                f"    - {spec_id} (add `## Acceptance Scenarios` with `### <title>` items)",
                file=sys.stderr,
            )
        return 1

    py_markers, dead = collect_python_markers_and_dead(BACKEND_TESTS)
    all_markers = py_markers | collect_ts_markers(FRONTEND_TS_ROOTS)

    markers_by_spec: dict[str, set[str]] = defaultdict(set)
    for spec_id, scenario in all_markers:
        markers_by_spec[spec_id].add(scenario)

    missing: list[tuple[str, str]] = []
    for spec_id, scenarios in specs.items():
        for s in sorted(scenarios - markers_by_spec.get(spec_id, set())):
            missing.append((spec_id, s))

    orphans: set[tuple[str, str]] = set()
    for spec_id, scenario in all_markers:
        if spec_id not in specs or scenario not in specs[spec_id]:
            orphans.add((spec_id, scenario))

    # `dead` (collected above in the same AST sweep): acceptance markers on
    # unconditionally-skipped tests report coverage that never executes —
    # treat as failure so function-, class-, or module-level `pytest.mark.skip`
    # can't mask a scenario as covered. (skipif/env-gated tests like the
    # benchmark suite are allowed; they run in a dedicated CI job.)
    if not missing and not orphans and not dead:
        if not args.quiet:
            total = sum(len(s) for s in specs.values())
            print(
                f"audit_acceptance: OK — {total} scenario(s) across "
                f"{len(specs)} spec(s) all covered."
            )
        return 0

    print("audit_acceptance: FAIL", file=sys.stderr)
    if missing:
        print("\n  Scenarios without test coverage:", file=sys.stderr)
        for spec_id, scenario in missing:
            print(f"    - {spec_id} :: {scenario}", file=sys.stderr)
    if orphans:
        print("\n  Test markers referring to unknown spec/scenario:", file=sys.stderr)
        for spec_id, scenario in sorted(orphans):
            print(f"    - {spec_id} :: {scenario}", file=sys.stderr)
    if dead:
        print(
            "\n  Acceptance markers on unconditionally-skipped tests "
            "(scenario reported covered but never runs):",
            file=sys.stderr,
        )
        for spec_id, scenario, loc in sorted(dead):
            print(f"    - {spec_id} :: {scenario}  ({loc})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
