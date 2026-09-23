#!/usr/bin/env python3
"""Audit acceptance-scenario coverage across spec.md files and test markers.

Convention (see .agents/testing.md "Acceptance Scenarios — Cross-Tier Markers"):
  * Spec scenarios live in `openspec/specs/<id>/spec.md` as OpenSpec
    `#### Scenario: <title>` headings, each inside the `### Requirement:` block
    it verifies, under `## Requirements`.
  * Spec ID is the spec directory's path relative to `openspec/specs/`, so it is
    the folder name for a top-level spec (`openspec/specs/mcp-gateway/spec.md`
    → 'mcp-gateway') and a slash-joined path for a nested child
    (`openspec/specs/channels/telegram/spec.md` → 'channels/telegram').
  * Scenario names are unique within a spec, because a marker names one.
  * Python tests carry `@pytest.mark.acceptance(spec="...", scenario="...")`.
  * TS tests use `test.acceptance("spec", "scenario", ...)`.
  * Rust tests carry a line comment directly above the test's attributes:

        // acceptance(spec = "desktop-app", scenario = "...")
        #[test]
        fn a_running_daemon_is_taken_over() { ... }

    Rust has no user-defined test attribute without a proc-macro crate, so the
    marker is a comment: read here, invisible to `cargo test`. It counts only
    when a `#[test]` / `#[tokio::test]` attribute follows it before the next
    `fn`, so a marker that drifts off its test stops counting rather than
    silently reporting a scenario covered. Stack several comments to cover
    several scenarios with one test. These tests run under `make desktop-test`,
    which `.github/workflows/desktop.yml` gates on every PR touching `desktop/`.

Exits non-zero on:
  * any scenario in spec.md without a matching marker (missing coverage)
  * any marker referring to a scenario / spec id that doesn't exist (orphan)
  * any marker on a test that can never run - `@pytest.mark.skip` (function,
    class or module level) in Python, `#[ignore]` in Rust - which would report
    a scenario covered while nothing ever executes

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
SPECS_DIR = REPO_ROOT / "openspec" / "specs"
BACKEND_TESTS = REPO_ROOT / "backend" / "tests"
# The frontend has no tier-by-directory layout: its tests are co-located
# `*.test.tsx` under src/. `frontend/tests/` was the first scaffold's shape and
# has been gone since the real web shell landed, so it is not listed here.
FRONTEND_TS_ROOTS = [
    REPO_ROOT / "frontend" / "src",
    REPO_ROOT / "e2e",
]
TS_SKIP_DIRS = {"node_modules", "dist", "build", ".next", "test-results"}
# The desktop shell is a Rust crate whose tests are `#[cfg(test)] mod tests`
# blocks inside the source files themselves, so the marker sweep is over
# `desktop/src/`, not a separate test tree.
RUST_ROOTS = [REPO_ROOT / "desktop" / "src"]

REQUIREMENTS_HEADER_RE = re.compile(r"^##\s+Requirements\s*$")
H2_RE = re.compile(r"^##\s")
OPENSPEC_SCENARIO_RE = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
# Matches the standalone acceptance helper exported from
# frontend/src/test/acceptance.ts. See .agents/testing.md.
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

# Rust marker: a `//` line comment carrying the same (spec, scenario) pair the
# other two tiers spell as a call. Named arguments (`spec = "..."`) mirror
# Python's keyword form rather than TS's positional one, because that is how a
# Rust attribute would have been written if one existed to write.
#
# Rust string literals are double-quoted only, so there is no single-quoted
# alternative to handle: a scenario title containing an apostrophe (e.g. "a
# Finder-launched app finds the user's real PATH") needs no special care.
#
# `^\s*//` (not `///`) keeps doc comments out: after `//` a doc comment has a
# third `/`, which matches neither `\s` nor `acceptance`.
RUST_ACCEPTANCE_RE = re.compile(
    r'^\s*//\s*acceptance\s*\(\s*'
    r'spec\s*=\s*"(?P<spec>[^"]+)"\s*,\s*'
    r'scenario\s*=\s*"(?P<scenario>[^"]+)"\s*,?\s*\)\s*$'
)
RUST_ATTR_RE = re.compile(r"^\s*#\[")
RUST_TEST_ATTR_RE = re.compile(r"^\s*#\[\s*(?:tokio::)?test\s*\]")
RUST_IGNORE_ATTR_RE = re.compile(r"^\s*#\[\s*ignore\b")


def _strip_ts_comments(text: str) -> str:
    text = TS_BLOCK_COMMENT_RE.sub("", text)
    text = TS_LINE_COMMENT_RE.sub("", text)
    return text


def _unfenced_lines(text: str) -> list[str]:
    """The lines outside fenced code blocks.

    A fence closes only on a run of the same character at least as long as the
    one that opened it, so a ```` fence can show a ``` block without the parser
    losing track of which side of the fence it is on.
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                continue
            out.append(line)
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
            fence = None
    return out


def parse_spec_scenarios(spec_md: Path) -> list[str]:
    """Scenario names in document order, duplicates kept so they can be flagged."""
    return _parse_openspec_scenarios(_unfenced_lines(spec_md.read_text(encoding="utf-8")))


def _parse_openspec_scenarios(lines: list[str]) -> list[str]:
    scenarios: list[str] = []
    in_requirements = False
    for line in lines:
        if REQUIREMENTS_HEADER_RE.match(line):
            in_requirements = True
            continue
        if in_requirements and H2_RE.match(line):
            in_requirements = False
            continue
        if in_requirements:
            m = OPENSPEC_SCENARIO_RE.match(line)
            if m:
                scenarios.append(m.group(1).strip())
    return scenarios


def _duplicates(names: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: list[str] = []
    for name in names:
        if name in seen and name not in dup:
            dup.append(name)
        seen.add(name)
    return dup


def collect_specs() -> tuple[dict[str, set[str]], list[str]]:
    """`({spec_id: {scenario, ...}}, [problem, ...])` for every spec.md at any
    depth under `openspec/specs/`.

    The spec id is the spec directory's path RELATIVE TO `openspec/specs/`, so a nested
    child spec is `channels/telegram` while a top-level one stays `channels`.
    The recursive glob and the relative id are what let a parent spec keep its
    own scenarios while its children carry theirs: a `*/spec.md` glob would see
    only the parent, and `spec_md.parent.name` would collapse
    `channels/telegram` and `agent-registry/telegram` onto the same id.

    A problem is a scenario name used twice within one spec.
    """
    out: dict[str, set[str]] = {}
    problems: list[str] = []
    if not SPECS_DIR.exists():
        return out, problems
    for spec_md in sorted(SPECS_DIR.rglob("spec.md")):
        spec_id = spec_md.parent.relative_to(SPECS_DIR).as_posix()
        names = parse_spec_scenarios(spec_md)
        for dup in _duplicates(names):
            problems.append(f"{spec_id}: scenario {dup!r} appears more than once")
        out[spec_id] = set(names)
    return out, problems


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


def _rust_marker_target(lines: list[str], start: int) -> tuple[bool, bool, str]:
    """Walk from a marker line to the item it annotates.

    Returns `(is_test, ignored, fn_name)`. Blank lines, further comments and
    other attributes (`#[cfg(unix)]`, a second acceptance marker) are skipped;
    the walk stops at the first line that is neither, which is the `fn`.
    """
    is_test = False
    ignored = False
    fn_name = ""
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if RUST_ATTR_RE.match(line):
            if RUST_TEST_ATTR_RE.match(line):
                is_test = True
            if RUST_IGNORE_ATTR_RE.match(line):
                ignored = True
            continue
        m = re.match(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)", line)
        fn_name = m.group("name") if m else stripped
        break
    return is_test, ignored, fn_name


def collect_rust_markers_and_dead(
    roots: list[Path],
) -> tuple[set[tuple[str, str]], list[tuple[str, str, str]]]:
    """Single sweep over the Rust sources -> (all markers, dead markers).

    A Rust marker is dead when its test carries `#[ignore]` - `cargo test`
    skips it, so the scenario would be reported covered while nothing runs.
    That is the same failure `@pytest.mark.skip` causes on the Python side.

    A marker with no `#[test]` beneath it is not recorded at all: it covers
    nothing, so its scenario resurfaces as missing coverage.
    """
    markers: set[tuple[str, str]] = set()
    dead: list[tuple[str, str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for src in sorted(root.rglob("*.rs")):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines):
                m = RUST_ACCEPTANCE_RE.match(line)
                if m is None:
                    continue
                is_test, ignored, fn_name = _rust_marker_target(lines, i)
                if not is_test:
                    continue
                pair = (m.group("spec"), m.group("scenario"))
                markers.add(pair)
                if ignored:
                    dead.append(
                        (
                            pair[0],
                            pair[1],
                            f"{src.relative_to(REPO_ROOT)}::{fn_name}",
                        )
                    )
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

    specs, problems = collect_specs()
    if problems:
        print("audit_acceptance: FAIL — malformed specs:", file=sys.stderr)
        for problem in problems:
            print(f"    - {problem}", file=sys.stderr)
        return 1
    if not specs:
        if not args.quiet:
            print("audit_acceptance: no openspec/specs/<id>/spec.md found — nothing to audit.")
        return 0

    # A spec.md with zero scenarios is almost certainly a malformed spec
    # (no `#### Scenario:` under `## Requirements`, or every one deleted).
    # Without this guard the audit silently passes as "0 missing coverage",
    # giving false confidence.
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
                f"    - {spec_id} (every `### Requirement:` needs a `#### Scenario:`)",
                file=sys.stderr,
            )
        return 1

    py_markers, dead = collect_python_markers_and_dead(BACKEND_TESTS)
    rs_markers, rs_dead = collect_rust_markers_and_dead(RUST_ROOTS)
    dead += rs_dead
    all_markers = py_markers | collect_ts_markers(FRONTEND_TS_ROOTS) | rs_markers

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
