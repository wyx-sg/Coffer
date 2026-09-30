"""The release pipeline's signing, notarization and updater feed (spec
desktop-app "Sign and notarise a release when its credentials are present",
"Check for updates against a signed release manifest").

None of it can run here — it needs a macOS runner, a Developer ID and the
updater key — so what is gated is what regresses silently: that every step
holding a secret is behind the plan step, that the plan says what it
skipped, that the access group stamped into the daemon is the one the
entitlements grant, and that the manifest the shell reads has the shape the
updater plugin expects.
"""

from __future__ import annotations

import json
import plistlib
import runpy
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.infrastructure.secret import build_identity

_REPO = Path(__file__).resolve().parents[4]
_RELEASE = _REPO / ".github" / "workflows" / "release.yml"
_SCRIPTS = _REPO / "scripts"
_ENTITLEMENTS = _REPO / "desktop" / "entitlements" / "coffer.entitlements.in"


def _script(name: str) -> dict[str, Any]:
    return runpy.run_path(str(_SCRIPTS / name))


def _steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(_RELEASE.read_text(encoding="utf-8"))
    return list(workflow["jobs"]["bundle"]["steps"])


def _step(name: str) -> dict[str, Any]:
    return next(s for s in _steps() if s.get("name") == name)


_ALL = dict.fromkeys(
    (
        "APPLE_CERTIFICATE",
        "APPLE_CERTIFICATE_PASSWORD",
        "APPLE_TEAM_ID",
        "APPLE_API_KEY",
        "APPLE_API_KEY_ID",
        "APPLE_API_ISSUER",
        "TAURI_SIGNING_PRIVATE_KEY",
        "COFFER_UPDATER_PUBKEY",
    ),
    True,
)


@pytest.mark.acceptance(
    spec="desktop-app", scenario="a release without signing credentials builds unsigned"
)
def test_without_credentials_every_signing_step_is_skipped_with_a_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _script("release_plan.py")["main"]
    out = tmp_path / "out"
    assert main([], env={"GITHUB_OUTPUT": str(out), "GITHUB_ACTIONS": "true"}) == 0
    assert out.read_text() == "codesign=false\nnotarize=false\nupdater=false\n"
    log = capsys.readouterr().out
    # One annotation per step, naming what is missing, visible on the run page.
    assert "::warning::Developer ID signing: SKIPPED — missing APPLE_CERTIFICATE" in log
    assert "::warning::Notarization: SKIPPED" in log
    assert "::warning::Updater: SKIPPED — missing TAURI_SIGNING_PRIVATE_KEY" in log

    # …and every step that would use a secret is behind that answer.
    for step in _steps():
        body = json.dumps(step)
        if "secrets." not in body or step.get("name") in {
            "plan release signing",
            "build the desktop app",
        }:
            continue
        assert "steps.plan.outputs." in str(step.get("if", "")), (
            f"step {step.get('name')!r} uses a secret without the plan's gate"
        )
    # The build step reads secrets only as presence checks or behind the plan.
    build_env = _step("build the desktop app")["env"]
    for key, value in build_env.items():
        if "secrets." in value and not key.startswith("HAS_"):
            assert key.startswith("TAURI_SIGNING_") or "steps.plan.outputs." in value, key


def test_the_plan_turns_each_step_on_only_with_all_it_needs(tmp_path: Path) -> None:
    plan = _script("release_plan.py")["plan"]
    everything = plan(_ALL)
    assert (everything.codesign, everything.notarize, everything.updater) == (True, True, True)
    # Notarization needs a signature first.
    no_cert = plan({**_ALL, "APPLE_CERTIFICATE": False})
    assert (no_cert.codesign, no_cert.notarize, no_cert.updater) == (False, False, True)
    # The updater is independent of Apple: a minisign key is enough.
    only_updater = plan({"TAURI_SIGNING_PRIVATE_KEY": True, "COFFER_UPDATER_PUBKEY": True})
    assert (only_updater.codesign, only_updater.updater) == (False, True)
    # A private key without the public key it pairs with ships an app that
    # could never verify an update, so it does not count.
    assert not plan({"TAURI_SIGNING_PRIVATE_KEY": True}).updater


@pytest.mark.acceptance(
    spec="desktop-app",
    scenario="a signed release carries the hardened runtime and its keychain access group",
)
def test_a_signed_build_is_hardened_and_stamped_with_one_access_group(tmp_path: Path) -> None:
    ns = _script("release_plan.py")
    config = ns["tauri_config"](
        ns["plan"](_ALL), entitlements="/tmp/coffer.entitlements", profile="/tmp/p"
    )
    assert config["bundle"]["macOS"] == {
        "hardenedRuntime": True,
        "entitlements": "/tmp/coffer.entitlements",
        "files": {"embedded.provisionprofile": "/tmp/p"},
    }
    assert config["bundle"]["createUpdaterArtifacts"] is True
    assert ns["tauri_config"](ns["plan"]({})) == {}

    # The entitlement grants exactly the group the daemon is stamped with.
    template = _ENTITLEMENTS.read_text(encoding="utf-8")
    entitlements = plistlib.loads(template.replace("@TEAM_ID@", "ABCDE12345").encode())
    assert entitlements == {"keychain-access-groups": ["ABCDE12345.coffer"]}
    assert "get-task-allow" not in template.split("-->")[-1]

    stamp = _script("stamp_build_identity.py")
    copy = tmp_path / "build_identity.py"
    shutil.copy(build_identity.__file__, copy)
    assert stamp["main"](["ABCDE12345"], target=copy) == 0
    assert 'KEYCHAIN_ACCESS_GROUP: str | None = "ABCDE12345.coffer"' in copy.read_text()
    with pytest.raises(SystemExit):
        stamp["access_group"]("not-a-team")
    # The tree itself is never stamped.
    assert build_identity.KEYCHAIN_ACCESS_GROUP is None

    # The binaries are signed by PyInstaller with the same identity and file.
    for spec in ("coffer-daemon.spec", "coffer.spec", "coffer-mcp-shim.spec"):
        text = (_REPO / "backend" / spec).read_text(encoding="utf-8")
        assert 'os.environ.get("COFFER_CODESIGN_IDENTITY")' in text, spec
        assert 'os.environ.get("COFFER_ENTITLEMENTS_FILE")' in text, spec
    # …and the pipeline proves it, then notarises and staples.
    verify = json.dumps(_step("verify the frozen binaries' signatures"))
    assert "release_signing.sh verify" in verify
    dmg = json.dumps(_step("notarize and staple the .dmg"))
    assert "release_signing.sh notarize" in dmg and "release_signing.sh staple" in dmg
    signing = (_SCRIPTS / "release_signing.sh").read_text(encoding="utf-8")
    assert "xcrun notarytool submit" in signing and "xcrun stapler staple" in signing
    assert 'grep -Eq "flags=.*runtime"' in signing


@pytest.mark.acceptance(spec="desktop-app", scenario="a release publishes the update manifest")
def test_the_release_publishes_a_signed_update_manifest(tmp_path: Path) -> None:
    make = _script("make_update_manifest.py")
    body = make["manifest"](
        version="v1.2.3",
        platform="darwin-aarch64",
        url="https://github.com/wyx-sg/Coffer/releases/download/v1.2.3/Coffer.app.tar.gz",
        signature="dW50cnVzdGVkIGNvbW1lbnQ=\n",
        notes="- Secrets have their own page.\n",
        pub_date=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
    )
    assert body == {
        "version": "1.2.3",
        "notes": "- Secrets have their own page.",
        "pub_date": "2026-09-27T12:00:00Z",
        "platforms": {
            "darwin-aarch64": {
                "signature": "dW50cnVzdGVkIGNvbW1lbnQ=",
                "url": "https://github.com/wyx-sg/Coffer/releases/download/v1.2.3/Coffer.app.tar.gz",
            }
        },
    }
    for bad in (
        {"version": "latest"},
        {"url": "http://example.com/x"},
        {"signature": "  "},
        {"platform": "macos"},
    ):
        args = {
            "version": "1.0.0",
            "platform": "darwin-aarch64",
            "url": "https://x/y",
            "signature": "s",
            **bad,
        }
        with pytest.raises(SystemExit):
            make["manifest"](**args)

    # The workflow writes it beside the archive and its signature, into the
    # artifacts the release job publishes.
    feed = json.dumps(_step("collect the updater archive and write latest.json"))
    assert "make_update_manifest.py" in feed
    assert "artifacts/latest.json" in feed and "$name.sig" in feed
    assert "releases/download/${tag}/${name}" in feed

    # The shell reads that file from the newest release, verifying the
    # signature and the version it was signed for.
    conf = json.loads((_REPO / "desktop" / "tauri.conf.json").read_text(encoding="utf-8"))
    updater = conf["plugins"]["updater"]
    assert updater["endpoints"] == [
        "https://github.com/wyx-sg/Coffer/releases/latest/download/latest.json"
    ]
    assert updater["requireSignedVersion"] is True
    # The public key is compiled in by the release (COFFER_UPDATER_PUBKEY),
    # never committed as a placeholder a build could ship.
    assert updater["pubkey"] == ""
    assert "createUpdaterArtifacts" not in conf["bundle"]
