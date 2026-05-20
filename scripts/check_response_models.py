#!/usr/bin/env python3
"""Enforce that every FastAPI route declares its wire shape.

Per agents/stack.md "HTTP Contracts (Wire Format)":

    Every HTTP route declares `response_model=<Foo>Response` against a
    Pydantic `BaseModel` — never `dict[str, Any]`.

This script AST-scans `backend/coffer/**/*.py` for FastAPI route decorators
(`@app.get`, `@router.post`, etc.) and fails on any that declare neither
`response_model=` nor `response_class=`. The `response_class=` carve-out
exists for streaming / file / no-body responses that legitimately have
no JSON schema.

Stdlib-only. Hooked into `make lint`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_PKG = REPO_ROOT / "backend" / "coffer"

ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
ACCEPTED_KWARGS = {"response_model", "response_class"}


def is_route_decorator(decorator: ast.expr) -> bool:
    """A decorator that looks like `@<owner>.<method>(...)` with method in ROUTE_METHODS."""
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return False
    return func.attr in ROUTE_METHODS


def declares_response_shape(decorator: ast.Call) -> bool:
    for kw in decorator.keywords:
        if kw.arg in ACCEPTED_KWARGS:
            return True
    return False


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return (lineno, function_name, decorator_repr) for each violation."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"check_response_models: cannot parse {path}: {e}", file=sys.stderr)
        return []

    violations: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if is_route_decorator(dec) and not declares_response_shape(dec):
                # Best-effort repr for the error message: `<owner>.<method>(...)`
                assert isinstance(dec, ast.Call)
                func_attr = dec.func
                assert isinstance(func_attr, ast.Attribute)
                owner = (
                    func_attr.value.id
                    if isinstance(func_attr.value, ast.Name)
                    else "<expr>"
                )
                repr_str = f"@{owner}.{func_attr.attr}(...)"
                violations.append((dec.lineno, node.name, repr_str))
    return violations


def main() -> int:
    if not BACKEND_PKG.exists():
        print(
            f"check_response_models: {BACKEND_PKG.relative_to(REPO_ROOT)} not present — skipping."
        )
        return 0

    files = sorted(BACKEND_PKG.rglob("*.py"))
    all_violations: list[tuple[Path, int, str, str]] = []
    for py in files:
        for lineno, name, repr_str in scan_file(py):
            all_violations.append((py, lineno, name, repr_str))

    if not all_violations:
        print(
            f"check_response_models: OK — {len(files)} file(s) scanned, all routes "
            f"declare response_model / response_class."
        )
        return 0

    print(
        "check_response_models: FAIL — routes without response_model / response_class:",
        file=sys.stderr,
    )
    for path, lineno, name, repr_str in all_violations:
        rel = path.relative_to(REPO_ROOT)
        print(f"  {rel}:{lineno}: {repr_str} → {name}()", file=sys.stderr)
    print(
        "\n  Declare `response_model=<Pydantic BaseModel>` (preferred) or "
        "`response_class=<FastAPI Response>` for streaming/file responses.",
        file=sys.stderr,
    )
    print(
        "  See agents/stack.md 'HTTP Contracts (Wire Format)'.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
