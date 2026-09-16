"""Static checks on the desktop shell's declared surface (spec desktop-app).

The shell is a Rust crate whose own `cargo test` suite no verification gate
runs. What CAN be gated from here is everything the scenario states about the
shell's *source and configuration* rather than its runtime: which plugins it
declares, what the webview is allowed to reach, and where its records go.
Those are the halves that regress silently — a re-added plugin or a widened
CSP is one line in a manifest nobody re-reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_DESKTOP = _REPO / "desktop"


def _capabilities() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((_DESKTOP / "capabilities").glob("*.json"))
    ]


@pytest.mark.acceptance(
    spec="desktop-app",
    scenario="the shell reimplements no daemon route",
)
def test_the_shell_declares_no_dialog_or_opener_plugin() -> None:
    """Native file actions belong to the daemon's HTTP routes in BOTH hosts.

    A dialog/opener plugin here would give the webview a second, Tauri-only
    path to the same operation, and the frontend would have to fan out on
    `isTauri()` again for something the user cannot perceive.
    """
    cargo = (_DESKTOP / "Cargo.toml").read_text(encoding="utf-8")
    executable = "\n".join(ln for ln in cargo.splitlines() if not ln.lstrip().startswith("#"))
    for plugin in ("tauri-plugin-dialog", "tauri-plugin-opener", "tauri-plugin-fs"):
        assert plugin not in executable, (
            f"{plugin} is declared in desktop/Cargo.toml; native file actions go "
            f"to the daemon over HTTP, not through a shell-only plugin"
        )

    caps = _capabilities()
    assert caps, "desktop/capabilities must declare at least the default capability"
    for cap in caps:
        for permission in cap.get("permissions", []):
            name = permission if isinstance(permission, str) else permission.get("identifier", "")
            assert not name.startswith(("dialog:", "opener:", "fs:", "shell:")), (
                f"capability {cap.get('identifier')!r} grants {name!r}; the webview "
                f"is allowed the core baseline and nothing more"
            )


@pytest.mark.acceptance(
    spec="desktop-app",
    scenario="the shell reimplements no daemon route",
)
def test_the_webview_content_policy_allows_loopback_and_ipc_and_nothing_else() -> None:
    """The page may reach this machine's daemon and the shell's own IPC. A
    remote origin in `connect-src` would make the app a browser for someone
    else's server while carrying a live daemon token."""
    conf = json.loads((_DESKTOP / "tauri.conf.json").read_text(encoding="utf-8"))
    csp = conf["app"]["security"]["csp"]
    connect = next(
        part.strip() for part in csp.split(";") if part.strip().startswith("connect-src")
    )
    sources = connect.split()[1:]
    assert sources, "connect-src must name its sources explicitly"
    allowed = {"'self'", "ipc:", "http://ipc.localhost"}
    for source in sources:
        assert source in allowed or source.startswith(("http://127.0.0.1", "http://localhost")), (
            f"connect-src allows {source!r}; only loopback and the shell's own IPC belong here"
        )


@pytest.mark.acceptance(
    spec="desktop-app",
    scenario="the shell's own records land in the daemon log",
)
def test_the_shell_writes_into_the_daemon_log_and_opens_no_second_file() -> None:
    """One log file, under the name the reader already knows.

    A second file would be invisible to the Activity page's daemon-log tab, to
    `coffer__diagnose`, and to the "check ~/.coffer/logs/daemon.log" line the
    CLI prints — so a tray restart failure would be recorded nowhere anyone
    looks. (That the records are actually written at runtime is the Rust
    crate's own test; what is gated here is the destination and the name.)
    """
    logging_rs = (_DESKTOP / "src" / "logging.rs").read_text(encoding="utf-8")
    assert 'const LOGGER_NAME: &str = "coffer.desktop";' in logging_rs, (
        "the shell's records must be attributable to `coffer.desktop`"
    )
    assert '.join("daemon.log")' in logging_rs, (
        "the shell must append to daemon.log rather than a file of its own"
    )

    # No other module may open a log file: every writer goes through
    # `logging::open_daemon_log`, which is what keeps it to one file.
    for rs in sorted((_DESKTOP / "src").glob("*.rs")):
        if rs.name == "logging.rs":
            continue
        text = rs.read_text(encoding="utf-8")
        executable = "\n".join(
            ln for ln in text.splitlines() if not ln.lstrip().startswith(("//", "//!"))
        )
        assert '.log"' not in executable, (
            f"{rs.name} names a log file of its own; the shell has exactly one, "
            f"opened through logging::open_daemon_log"
        )
