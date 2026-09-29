#!/usr/bin/env python3
"""Decide which signing steps a release run can take, and say why.

    python scripts/release_plan.py                       # decide, and say why
    python scripts/release_plan.py tauri-config OUT \
        [--entitlements PLIST] [--profile PROFILE]       # the `tauri build --config`

Every signing step of ``.github/workflows/release.yml`` is gated on the
credentials it needs being present, so a fork, a pull request's dispatch, or
this repository before the owner has bought a Developer Program membership
still builds a (unsigned) release and stays green. The workflow passes each
secret's *presence* — never its value — as a ``HAS_<NAME>`` environment
variable (``true``/``false``); this prints one line per step saying whether it
runs and, when it does not, exactly which secret or variable is missing, and
writes the answers to ``$GITHUB_OUTPUT`` for the steps' ``if:``. What each
secret is and how to create it is in ``RELEASING.md``. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Each gated step and the credentials it needs, by the name the workflow uses.
DEVELOPER_ID = ("APPLE_CERTIFICATE", "APPLE_CERTIFICATE_PASSWORD", "APPLE_TEAM_ID")
NOTARY = ("APPLE_API_KEY", "APPLE_API_KEY_ID", "APPLE_API_ISSUER")
# The key's password is optional (a key generated without one has none), and
# the public key is a repository *variable*, not a secret: it ships in the app.
UPDATER = ("TAURI_SIGNING_PRIVATE_KEY", "COFFER_UPDATER_PUBKEY")


@dataclass(frozen=True)
class Plan:
    codesign: bool
    notarize: bool
    updater: bool
    #: One ``(runs, message)`` per gated step.
    lines: tuple[tuple[bool, str], ...]


def _missing(present: dict[str, bool], names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not present.get(n, False)]


def plan(present: dict[str, bool]) -> Plan:
    """What runs, given which credentials are present."""
    lines: list[tuple[bool, str]] = []
    missing_id = _missing(present, DEVELOPER_ID)
    codesign = not missing_id
    if codesign:
        lines.append((True, "Developer ID signing: ON — binaries and app signed, hardened runtime"))
    else:
        lines.append(
            (
                False,
                "Developer ID signing: SKIPPED — missing "
                + ", ".join(missing_id)
                + "; the release is unsigned (Coffer-unsigned-*.dmg) and needs the xattr step",
            )
        )
    missing_notary = _missing(present, NOTARY)
    notarize = codesign and not missing_notary
    if notarize:
        lines.append((True, "Notarization: ON — notarytool submit, then staple the app and .dmg"))
    elif not codesign:
        lines.append((False, "Notarization: SKIPPED — needs Developer ID signing first"))
    else:
        lines.append((False, "Notarization: SKIPPED — missing " + ", ".join(missing_notary)))
    missing_updater = _missing(present, UPDATER)
    updater = not missing_updater
    if updater:
        lines.append((True, "Updater: ON — updater archive signed, latest.json published"))
    else:
        lines.append(
            (
                False,
                "Updater: SKIPPED — missing "
                + ", ".join(missing_updater)
                + "; the app built here cannot update itself",
            )
        )
    return Plan(codesign=codesign, notarize=notarize, updater=updater, lines=tuple(lines))


def tauri_config(
    result: Plan, *, entitlements: str | None = None, profile: str | None = None
) -> dict[str, object]:
    """The configuration merged over ``desktop/tauri.conf.json`` for this run.

    Signing needs the entitlements (the keychain access group) and, where the
    entitlement needs one, the provisioning profile embedded in the app; the
    identity itself reaches Tauri as ``APPLE_SIGNING_IDENTITY``. The updater
    archive is only produced when the updater key is present, because
    ``createUpdaterArtifacts`` without it fails the build.
    """
    bundle: dict[str, object] = {}
    if result.codesign:
        mac: dict[str, object] = {"hardenedRuntime": True}
        if entitlements:
            mac["entitlements"] = entitlements
        if profile:
            mac["files"] = {"embedded.provisionprofile": profile}
        bundle["macOS"] = mac
    if result.updater:
        bundle["createUpdaterArtifacts"] = True
    return {"bundle": bundle} if bundle else {}


def _present_from_env(env: dict[str, str]) -> dict[str, bool]:
    names = DEVELOPER_ID + NOTARY + UPDATER
    return {n: env.get(f"HAS_{n}", "false").strip().lower() == "true" for n in names}


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    env = dict(os.environ) if env is None else env
    result = plan(_present_from_env(env))
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    config = sub.add_parser("tauri-config")
    config.add_argument("out", type=Path)
    config.add_argument("--entitlements")
    config.add_argument("--profile")
    args = parser.parse_args(argv)
    if args.command == "tauri-config":
        body = tauri_config(result, entitlements=args.entitlements, profile=args.profile)
        args.out.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        print(f"release_plan: tauri config → {args.out}: {json.dumps(body)}")
        return 0
    for runs, line in result.lines:
        # A workflow annotation, so a skipped step is visible on the run page.
        kind = "notice" if runs else "warning"
        print(f"::{kind}::{line}" if env.get("GITHUB_ACTIONS") else line)
    out = env.get("GITHUB_OUTPUT")
    if out:
        with Path(out).open("a", encoding="utf-8") as fh:
            fh.write(f"codesign={str(result.codesign).lower()}\n")
            fh.write(f"notarize={str(result.notarize).lower()}\n")
            fh.write(f"updater={str(result.updater).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
