#!/usr/bin/env python3
"""Dump the backend error codes + audit event types the frontend must localize.

The output is a checked-in JSON fixture
(``frontend/src/i18n/backend-keys.fixture.json``) that the frontend i18n parity
test diffs against ``locales/{en,zh}.json``. Re-run this whenever a new
``CofferError`` subclass or ``AuditEventType`` value lands so the fixture — and
therefore the locale-coverage guard — stays in sync:

    ./.venv/bin/python scripts/dump_i18n_backend_keys.py

It is intentionally generated rather than hand-maintained: the source of truth
is the Python enums, and a stale fixture would let untranslated codes ship
silently — the exact drift this guard exists to prevent.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE = _REPO_ROOT / "frontend" / "src" / "i18n" / "backend-keys.fixture.json"


def _error_codes() -> list[str]:
    """Every ``.code`` reachable on a ``CofferError`` subclass, plus the synthetic
    envelope codes the HTTP layer emits for bare ``HTTPException``s."""
    import coffer
    from coffer.domain.error_base import CofferError

    codes: set[str] = set()
    for mod in pkgutil.walk_packages(coffer.__path__, "coffer."):
        try:
            module = importlib.import_module(mod.name)
        except Exception:  # noqa: BLE001 - optional deps in some submodules
            continue
        for _name, obj in vars(module).items():
            if inspect.isclass(obj) and issubclass(obj, CofferError):
                codes.add(obj.code)

    from coffer.surfaces.http import errors as http_errors

    codes |= set(http_errors._STATUS)
    codes |= set(http_errors._HTTP_CODE.values())
    return sorted(codes)


def _audit_events() -> list[str]:
    from coffer.domain.audit import AuditEventType

    return sorted(e.value for e in AuditEventType)


def build() -> dict[str, list[str]]:
    return {"errorCodes": _error_codes(), "auditEvents": _audit_events()}


def main() -> None:
    payload = build()
    _FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    print(
        f"wrote {len(payload['errorCodes'])} error codes + "
        f"{len(payload['auditEvents'])} audit events to {_FIXTURE}"
    )


if __name__ == "__main__":
    main()
