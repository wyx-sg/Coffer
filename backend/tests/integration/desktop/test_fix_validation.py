"""Static fix-validation tests for PR #24 review findings (CODE24-*).

These tests cross-check the Rust source + capabilities + Tauri config to
make sure the review fixes for the macOS sidecar path bug, the
detect-or-spawn / rate-limit additions to restart_daemon, the version
sentinel, and the redundant capability cleanup don't silently regress.

Static (string-level) checks only — we don't compile the desktop crate
here. The cargo unit tests inside src/tray.rs cover the close-to-tray
logic at the Rust level; CI exercises the full bundle via the GitHub
Actions release workflow + scripts/smoke_test_bundle.sh.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_DESKTOP = Path(__file__).resolve().parents[4] / "desktop"


def _src(name: str) -> str:
    return (_DESKTOP / "src" / name).read_text()


def test_macos_sidecar_path_probes_contents_macos() -> None:
    """CODE24-005: Tauri puts externalBin in Contents/MacOS, not Resources.

    Both the shim and daemon path probes must explicitly join
    ``parent/MacOS`` before falling back to the resource dir.
    """
    shim_rs = _src("shim.rs")
    daemon_rs = _src("daemon.rs")
    assert '"MacOS"' in shim_rs, "shim.rs must probe Contents/MacOS for sidecar binary"
    assert '"MacOS"' in daemon_rs, "daemon.rs must probe Contents/MacOS for daemon binary"


def test_version_sentinel_used_for_shim_staleness() -> None:
    """CODE24-012: size-equality alone misses cross-version same-size builds.

    The shim deploy logic must consult a `.version` sentinel plus mtime.
    """
    shim_rs = _src("shim.rs")
    assert "APP_VERSION" in shim_rs, "shim.rs must capture CARGO_PKG_VERSION"
    assert 'env!("CARGO_PKG_VERSION")' in shim_rs, (
        "shim.rs must bake the Cargo version into APP_VERSION"
    )
    assert "shim_version_sentinel_path" in shim_rs, "shim.rs must define a sentinel-path helper"
    assert ".coffer-mcp-shim.version" in shim_rs, "sentinel filename must be stable"
    assert "modified()" in shim_rs, "staleness check must also compare mtime"


def test_restart_daemon_has_detect_or_spawn() -> None:
    """CODE24-009: restart_daemon must short-circuit if a daemon already runs."""
    daemon_rs = _src("daemon.rs")
    assert "read_daemon_port" in daemon_rs, "daemon.rs must define a port reader"
    assert "daemon_is_listening" in daemon_rs, "daemon.rs must define a listener probe"
    assert "TcpStream::connect_timeout" in daemon_rs, (
        "daemon.rs must use a bounded-timeout TCP probe (no hang on no-route)"
    )
    assert "started: false" in daemon_rs, (
        "daemon.rs must report started=false on the already-running branch"
    )


def test_restart_daemon_has_rate_limit() -> None:
    """CODE24-023: protect against runaway repeat spawns."""
    daemon_rs = _src("daemon.rs")
    assert "LAST_RESTART_AT" in daemon_rs, "daemon.rs must track last-restart timestamp"
    assert "RESTART_MIN_INTERVAL_SECS" in daemon_rs, "daemon.rs must define the rate-limit interval"
    assert "rate-limited" in daemon_rs, "rate-limit must produce a clear error"


def test_tray_icon_uses_expect_not_unwrap() -> None:
    """CODE24-013: prefer .expect(\"reason\") over bare .unwrap()."""
    tray_rs = _src("tray.rs")
    # The icon construction line is the only known unwrap site in this crate.
    assert ".unwrap()" not in tray_rs, "tray.rs must not contain bare .unwrap() calls"
    assert ".expect(" in tray_rs, "tray.rs must use .expect() for the tray icon"


def test_capabilities_no_redundant_path_default() -> None:
    """CODE24-008: core:default already includes core:path:default in Tauri 2.x."""
    capabilities = json.loads((_DESKTOP / "capabilities" / "default.json").read_text())
    perms = capabilities.get("permissions", [])
    assert "core:default" in perms, "capability must keep core:default"
    assert "core:path:default" not in perms, (
        "core:path:default is implied by core:default — remove redundancy"
    )


def test_entitlements_placeholder_exists() -> None:
    """CODE24-020: placeholder entitlements.plist ready for when signing is wired."""
    plist = _DESKTOP / "entitlements.plist"
    assert plist.exists(), "desktop/entitlements.plist must exist as a placeholder"
    content = plist.read_text()
    assert "hardened" in content.lower() or "library-validation" in content, (
        "entitlements.plist must reference hardened-runtime keys"
    )


@pytest.mark.parametrize(
    "mod,limit",
    [
        ("lib.rs", 400),
        ("shim.rs", 400),
        ("daemon.rs", 400),
        ("tray.rs", 400),
    ],
)
def test_desktop_modules_under_size_cap(mod: str, limit: int) -> None:
    """CODE24-007: keep each desktop source file under the 400-line cap.

    The original lib.rs reached 532 lines after fixes; we split it into
    sibling modules. This guards against future drift.
    """
    path = _DESKTOP / "src" / mod
    assert path.exists(), f"expected desktop/src/{mod}"
    lines = path.read_text().splitlines()
    assert len(lines) <= limit, f"{mod}: {len(lines)} lines > {limit} cap"
