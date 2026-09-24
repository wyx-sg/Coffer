#!/usr/bin/env python3
"""Keep the generated reference pages level with the code they describe.

`docs-site/reference/cli.md` and `docs-site/reference/rest-api.md` are
generated: the first from the Typer command tree, the second from the daemon's
OpenAPI document. A command, option or route added without regenerating them
leaves the published reference silently wrong, so this regenerates both in
memory and fails when either file differs from what the code produces.

Fix a failure with `make docs-reference` and commit the result.

Needs the backend importable (run it with the project venv, as `make lint`
does). Exits non-zero with one line per stale page.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "docs-site" / "scripts"

GENERATORS = ("gen_cli_reference", "gen_rest_reference")


def _load(name: str):  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    stale: list[str] = []
    for name in GENERATORS:
        module = _load(name)
        expected = module.render()
        path: Path = module.OUTPUT
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual != expected:
            stale.append(str(path.relative_to(REPO_ROOT)))
    for rel in stale:
        print(f"check_cli_reference: {rel} is stale — run `make docs-reference`", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
