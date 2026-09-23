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


_FRONTEND_SRC = _REPO / "frontend" / "src"

# The only frontend modules allowed to know which host they run in: the
# credential supplier itself, and the offline banner whose Restart control only
# the shell can offer.
_HOST_AWARE_MODULES = {
    Path("lib/tauri.ts"),
    Path("components/DaemonOfflineBanner.tsx"),
}


@pytest.mark.acceptance(
    spec="desktop-app",
    scenario="the shell hosts the one build the daemon serves",
)
def test_the_shell_and_the_frozen_daemon_ship_the_same_frontend_build() -> None:
    """Both hosts name the one `frontend/dist`, built by the one `npm run build`.

    A second build (or a second directory) is how the two hosts drift: the
    shell would ship a UI the daemon never serves, and a bug report from one
    host would not reproduce in the other.
    """
    conf = json.loads((_DESKTOP / "tauri.conf.json").read_text(encoding="utf-8"))
    build = conf["build"]
    assert (_DESKTOP / build["frontendDist"]).resolve() == (_REPO / "frontend" / "dist"), (
        f"tauri.conf.json frontendDist {build['frontendDist']!r} must be the repo's frontend/dist"
    )
    assert build["beforeBuildCommand"] == "npm run build --prefix frontend", (
        "the shell must build the UI with the frontend's own build script, not a variant of it"
    )

    daemon_spec = (_REPO / "backend" / "coffer-daemon.spec").read_text(encoding="utf-8")
    assert '"..", "frontend", "dist"' in daemon_spec and '(_webui_dist, "webui")' in daemon_spec, (
        "the frozen daemon must ship the same frontend/dist the shell bundles"
    )

    package = json.loads((_REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    builds = sorted(name for name in package["scripts"] if name.startswith("build"))
    assert builds == ["build"], f"the frontend must have exactly one UI build; found {builds}"
    vite_configs = sorted(p.name for p in (_REPO / "frontend").glob("vite*.config.*"))
    assert vite_configs == ["vite.config.ts"], (
        f"a second Vite config is a second UI build; found {vite_configs}"
    )

    host_aware: set[Path] = set()
    scanned = 0
    for source in _FRONTEND_SRC.rglob("*.ts*"):
        if ".test." in source.name:
            continue
        scanned += 1
        text = source.read_text(encoding="utf-8")
        if "isTauri(" in text or "__TAURI" in text or "@tauri-apps/api" in text:
            host_aware.add(source.relative_to(_FRONTEND_SRC))
    assert scanned > 50, "the frontend source tree was not found"
    assert host_aware <= _HOST_AWARE_MODULES, (
        f"only the credential supplier and the offline banner may branch on the host; "
        f"also branching: {sorted(str(p) for p in host_aware - _HOST_AWARE_MODULES)}"
    )
    assert Path("lib/tauri.ts") in host_aware, "the credential supplier must be the host-aware seam"


def _csp_directives() -> dict[str, list[str]]:
    conf = json.loads((_DESKTOP / "tauri.conf.json").read_text(encoding="utf-8"))
    directives: dict[str, list[str]] = {}
    for part in conf["app"]["security"]["csp"].split(";"):
        words = part.split()
        if words:
            directives[words[0]] = words[1:]
    return directives


@pytest.mark.acceptance(
    spec="desktop-app",
    scenario="the content policy admits loopback on any port and the bundle's own scripts",
)
def test_the_content_policy_admits_any_loopback_port_and_only_bundled_code() -> None:
    """The port is only known after the handshake, so loopback must be
    port-wildcarded; everything else the page loads must come from the bundle."""
    csp = _csp_directives()

    assert csp.get("default-src") == ["'self'"], (
        f"default-src must fall back to the bundle only; got {csp.get('default-src')}"
    )

    connect = csp["connect-src"]
    assert any(src in ("http://127.0.0.1:*", "http://localhost:*") for src in connect), (
        f"connect-src must admit a loopback origin on any port; got {connect}"
    )
    assert any(src in ("ipc:", "http://ipc.localhost") for src in connect), (
        f"connect-src must admit the shell's IPC scheme; got {connect}"
    )
    loopback_or_ipc = {"'self'", "ipc:", "http://ipc.localhost"}
    for src in connect:
        host = src.split("://", 1)[-1].split(":", 1)[0].split("/", 1)[0]
        assert src in loopback_or_ipc or host in {"127.0.0.1", "localhost", "[::1]"}, (
            f"connect-src admits {src!r}, which is neither loopback nor IPC"
        )

    assert csp.get("script-src") == ["'self'"], (
        f"scripts must load only from the bundle; got {csp.get('script-src')}"
    )
    assert set(csp.get("style-src", [])) <= {"'self'", "'unsafe-inline'"}, (
        f"styles must come from the bundle or inline in it; got {csp.get('style-src')}"
    )
    assert "'self'" in csp.get("style-src", []), "style-src must admit the bundle's stylesheets"
    for directive, sources in csp.items():
        for src in sources:
            assert not src.startswith("https://"), (
                f"{directive} admits the remote origin {src!r}; the page loads nothing remote"
            )


_APP_QUARANTINE_STEP = "xattr -dr com.apple.quarantine /Applications/Coffer.app"


def _release_notes() -> str:
    """The body the release job publishes: the heredoc ending at `NOTES`."""
    text = (_REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    start = text.index("<<'NOTES'")
    end = text.index("\n", text.index("\n          NOTES\n", start) + 1)
    return text[start:end]


@pytest.mark.acceptance(
    spec="desktop-app",
    scenario="the install instructions carry the quarantine-clearing step for the app",
)
def test_release_notes_and_readme_carry_the_app_quarantine_step() -> None:
    """An unsigned, browser-downloaded `.dmg` is refused on double-click as
    "damaged"; the one command that fixes it must be where the user looks."""
    notes = _release_notes()
    assert _APP_QUARANTINE_STEP in notes, "the release notes must carry the app's xattr step"

    # Same notice as the terminal tier's step — not buried somewhere else.
    notice = [ln for ln in notes.splitlines() if ln.strip().startswith(">")]
    notice_text = "\n".join(notice)
    assert _APP_QUARANTINE_STEP in notice_text, "the app's step must be in the quarantine notice"
    assert "xattr -dr com.apple.quarantine <extracted-directory>" in notice_text, (
        "the terminal tier's step must be in that same notice"
    )

    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    assert _APP_QUARANTINE_STEP in readme, "the README must carry the app's xattr step"
    assert "xattr -dr com.apple.quarantine ~/.coffer/bin" in readme, (
        "the README carries the terminal tier's step; the app's must sit beside it"
    )
