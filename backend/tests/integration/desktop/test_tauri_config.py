"""Verify Tauri tray + close-to-tray + autolaunch are wired.

These are "wiring" tests — they read the Rust source and config files
and confirm the right symbols are referenced. They don't run the
actual desktop app (Tauri's runtime tests would need a headless GUI
+ a built binary). They're sufficient to catch regressions like
accidentally removing the tray icon or the close interception.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_DESKTOP = Path(__file__).resolve().parents[4] / "desktop"


def _all_rust_sources() -> str:
    """Concatenate every .rs file under desktop/src/ for symbol search.

    The desktop crate is split into modules (lib.rs orchestrator + shim.rs +
    daemon.rs + tray.rs) to stay under the project's 400-line-per-file cap,
    so these wiring assertions look across the whole crate rather than at
    lib.rs alone.
    """
    src = _DESKTOP / "src"
    return "\n".join(p.read_text() for p in sorted(src.glob("*.rs")))


@pytest.mark.acceptance(spec="003-mcp-gateway-desktop", scenario="launch at login")
def test_autostart_plugin_wired() -> None:
    sources = _all_rust_sources()
    cargo_toml = (_DESKTOP / "Cargo.toml").read_text()
    capabilities = json.loads((_DESKTOP / "capabilities" / "default.json").read_text())

    assert "tauri-plugin-autostart" in cargo_toml, "Cargo.toml must declare the autostart plugin"
    assert "tauri_plugin_autostart" in sources, "crate must register the autostart plugin"
    assert "set_autostart_enabled" in sources, "crate must expose the set_autostart_enabled command"
    assert "get_autostart_enabled" in sources, "crate must expose the get_autostart_enabled command"
    assert "autostart:default" in capabilities.get("permissions", []), (
        "default capability must grant autostart:default"
    )


@pytest.mark.acceptance(spec="003-mcp-gateway-desktop", scenario="close to tray, not exit")
def test_tray_and_close_interception_wired() -> None:
    sources = _all_rust_sources()
    capabilities = json.loads((_DESKTOP / "capabilities" / "default.json").read_text())

    # Tray icon construction (lives in tray.rs).
    assert "TrayIconBuilder" in sources, "crate must build a tray icon"
    assert '"open"' in sources, "tray menu must include an Open item"
    assert '"quit"' in sources, "tray menu must include a Quit item"

    # Close-request interception (in lib.rs entry point).
    assert "CloseRequested" in sources and "prevent_close()" in sources, (
        "crate must intercept window close and prevent it"
    )

    # ExitRequested interception (so closing the last window doesn't kill the app).
    assert "ExitRequested" in sources and "prevent_exit()" in sources, (
        "crate must intercept exit request when last window is closed"
    )

    # Window-control permissions
    perms = capabilities.get("permissions", [])
    assert "core:window:allow-show" in perms
    assert "core:window:allow-hide" in perms
    assert "core:tray:default" in perms
