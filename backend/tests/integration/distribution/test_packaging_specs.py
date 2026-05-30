"""Static checks on PyInstaller specs + Tauri sidecar wiring.

Does NOT actually build binaries — that's done by `make bundle-binaries`
and (in CI) the cross-platform GitHub Actions matrix. These tests just
verify the configuration files are present + structurally correct, so
broken wiring is caught early.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# AST helpers for parsing PyInstaller spec files
# ---------------------------------------------------------------------------


def _parse_spec(spec_path: Path) -> ast.Module:
    """Parse a PyInstaller .spec file as a Python AST module."""
    return ast.parse(spec_path.read_text())


def _find_calls(tree: ast.AST, func_name: str) -> list[ast.Call]:
    """Find every top-level call `func_name(...)` in `tree`.

    PyInstaller specs use unqualified bare names (`Analysis`, `EXE`, `PYZ`),
    so we only match `Call(func=Name(id=func_name))` — not attribute calls.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == func_name
    ]


def _get_kw(call: ast.Call, name: str) -> ast.expr | None:
    """Return the keyword argument node named `name`, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _extract_str_list(node: ast.expr | None) -> list[str]:
    """Return string constants from a List/Tuple node, or []."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    out: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
    return out


def _collect_submodules_args(tree: ast.AST) -> set[str]:
    """Return the first-positional-arg string for every collect_submodules() call."""
    args: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "collect_submodules"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            args.add(node.args[0].value)
    return args


def _collect_hidden_string_literals(tree: ast.AST) -> set[str]:
    """Return string literals appearing inside list/tuple constructors at
    module scope. Used to verify hidden imports like 'anyio._backends._asyncio'.
    """
    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    literals.add(elt.value)
    return literals


# ---------------------------------------------------------------------------
# Spec sanity tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec_name,expected_target_module",
    [
        ("coffer-daemon.spec", "coffer/infrastructure/daemon/entry.py"),
        ("coffer-mcp-shim.spec", "coffer/surfaces/shim/main.py"),
    ],
)
def test_pyinstaller_spec_present_and_valid(spec_name: str, expected_target_module: str) -> None:
    spec_path = _REPO / "backend" / spec_name
    assert spec_path.exists(), f"missing {spec_path}"
    tree = _parse_spec(spec_path)

    # Analysis(...) is required; its first positional argument is the script
    # list, whose first element must be the entry module.
    analyses = _find_calls(tree, "Analysis")
    assert analyses, f"{spec_name}: must call Analysis(...)"
    analysis = analyses[0]
    assert analysis.args, f"{spec_name}: Analysis(...) needs a script list as first arg"
    scripts = _extract_str_list(analysis.args[0])
    assert scripts, f"{spec_name}: Analysis() first arg must be a list of script paths"
    assert any(expected_target_module in s for s in scripts), (
        f"{spec_name}: Analysis() script list {scripts} does not include {expected_target_module}"
    )

    # EXE(...) is required; console=True must be set explicitly so the
    # daemon writes to stderr and the shim uses stdin/stdout.
    exes = _find_calls(tree, "EXE")
    assert exes, f"{spec_name}: must call EXE(...)"
    exe = exes[0]
    console_kw = _get_kw(exe, "console")
    assert isinstance(console_kw, ast.Constant) and console_kw.value is True, (
        f"{spec_name}: EXE(console=True) must be set so the binary keeps a console"
    )


def test_tauri_externalbin_lists_both_binaries() -> None:
    # Tauri 2.x flat layout — assert directly. If the schema changes a major
    # version, let KeyError fail loudly so we update tests + config together.
    tauri_conf = json.loads((_REPO / "desktop" / "tauri.conf.json").read_text())
    external_bins = tauri_conf["bundle"]["externalBin"]
    paths = {Path(p).name for p in external_bins}
    assert "coffer-daemon" in paths, "tauri.conf.json bundle.externalBin must list coffer-daemon"
    assert "coffer-mcp-shim" in paths, (
        "tauri.conf.json bundle.externalBin must list coffer-mcp-shim"
    )


def test_build_script_present_and_executable() -> None:
    script = _REPO / "scripts" / "build_binaries.sh"
    assert script.exists(), "scripts/build_binaries.sh missing"
    # Must be readable
    contents = script.read_text()
    assert "pyinstaller" in contents.lower()
    assert "desktop/binaries" in contents


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX exec bit not preserved on Windows checkouts",
)
def test_build_script_executable_bit_on_posix() -> None:
    script = _REPO / "scripts" / "build_binaries.sh"
    assert os.access(script, os.X_OK), "build_binaries.sh must be executable on POSIX"


def test_makefile_has_bundle_binaries_target() -> None:
    makefile = (_REPO / "Makefile").read_text()
    assert "bundle-binaries" in makefile, "Makefile must have a bundle-binaries target"


def test_pyinstaller_in_dev_deps() -> None:
    pyproject = (_REPO / "backend" / "pyproject.toml").read_text()
    assert "pyinstaller" in pyproject.lower(), (
        "backend/pyproject.toml must declare pyinstaller in dev deps"
    )


# ---------------------------------------------------------------------------
# Cross-correlation: PyInstaller `name=` ↔ Tauri externalBin basenames
# ---------------------------------------------------------------------------


def test_pyinstaller_exe_names_match_tauri_externalbin() -> None:
    """The `name=` of each EXE() in the .spec files must equal the basename
    of an externalBin entry in tauri.conf.json. If either side drifts (e.g.
    rename the daemon binary in the spec but forget to update tauri.conf),
    the Tauri build links the wrong sidecar — caught here at the static
    config layer instead of at install time on the user's machine."""
    spec_names: set[str] = set()
    for spec_name in ("coffer-daemon.spec", "coffer-mcp-shim.spec"):
        tree = _parse_spec(_REPO / "backend" / spec_name)
        for exe in _find_calls(tree, "EXE"):
            name_kw = _get_kw(exe, "name")
            assert isinstance(name_kw, ast.Constant) and isinstance(name_kw.value, str), (
                f"{spec_name}: EXE(name=...) must be a string literal"
            )
            spec_names.add(name_kw.value)

    tauri_conf = json.loads((_REPO / "desktop" / "tauri.conf.json").read_text())
    external_basenames = {Path(p).name for p in tauri_conf["bundle"]["externalBin"]}

    missing = spec_names - external_basenames
    assert not missing, (
        f"PyInstaller EXE name(s) {missing} not present in tauri.conf.json bundle.externalBin "
        f"(externalBin basenames: {external_basenames}). "
        "Rename one side without the other → Tauri bundles a non-existent sidecar."
    )


# ---------------------------------------------------------------------------
# Critical hidden imports + migration data
# ---------------------------------------------------------------------------


def test_daemon_spec_includes_critical_hidden_imports() -> None:
    """The daemon spec must declare hidden imports for modules PyInstaller's
    static analysis cannot see: anyio's runtime-selected asyncio backend, and
    alembic + mcp submodules that are loaded dynamically. Without these, the
    PyInstaller-packaged daemon crashes on first import at runtime."""
    tree = _parse_spec(_REPO / "backend" / "coffer-daemon.spec")

    submodules = _collect_submodules_args(tree)
    assert "alembic" in submodules, (
        "daemon spec must call collect_submodules('alembic') — alembic loads "
        "migrations dynamically and PyInstaller cannot detect them statically"
    )
    assert "mcp" in submodules, (
        "daemon spec must call collect_submodules('mcp') — the MCP SDK loads transports dynamically"
    )

    literals = _collect_hidden_string_literals(tree)
    assert "anyio._backends._asyncio" in literals, (
        "daemon spec must list 'anyio._backends._asyncio' as a hidden import — "
        "anyio chooses the backend at runtime via sniffio and PyInstaller "
        "misses it otherwise"
    )


def test_daemon_spec_ships_migrations_directory() -> None:
    """The daemon must ship the alembic migrations directory as a data file so
    `upgrade head` can run against a fresh DB on first launch. If this drops
    out, brand-new installs fail with `KeyError: 'no such revision'`."""
    tree = _parse_spec(_REPO / "backend" / "coffer-daemon.spec")

    # The build runs pyinstaller from backend/ (ADR-008 build_binaries.sh), so
    # the data-file source path is relative to backend/ — "coffer/…", not
    # "backend/coffer/…". Both src and dst are the package-relative path.
    migrations_src = "coffer/infrastructure/persistence/migrations"
    migrations_dst = "coffer/infrastructure/persistence/migrations"

    # Look for a tuple literal carrying the two paths anywhere in datas.
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) == 2:
            elts = node.elts
            if (
                isinstance(elts[0], ast.Constant)
                and isinstance(elts[1], ast.Constant)
                and elts[0].value == migrations_src
                and elts[1].value == migrations_dst
            ):
                found = True
                break
    assert found, (
        "daemon spec must include the migrations data tuple "
        f"({migrations_src!r}, {migrations_dst!r}) in datas"
    )


def test_shim_spec_includes_anyio_backend_hidden_import() -> None:
    """The shim is anyio-based too; it crashes on first await without the
    runtime-selected backend listed explicitly."""
    tree = _parse_spec(_REPO / "backend" / "coffer-mcp-shim.spec")
    literals = _collect_hidden_string_literals(tree)
    assert "anyio._backends._asyncio" in literals, (
        "shim spec must list 'anyio._backends._asyncio' as a hidden import"
    )


# ---------------------------------------------------------------------------
# SPEC24-018 build-pipeline acceptance scenarios
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="003-mcp-gateway-desktop",
    scenario="release tag produces both the CLI-only archives and the desktop installers",
)
def test_release_workflow_produces_platform_artifact_matrix() -> None:
    """The release workflow must define a matrix that produces the supported
    platforms — macOS arm64 (Apple Silicon) and Linux x64 — and ship a SHA-256
    checksum alongside each installer. macOS x64 (Intel, macos-13) and Windows
    are intentionally NOT built (Intel runners are deprecated/starved and
    PyInstaller can't cross-compile them). The actual build runs in CI on tag
    push; this asserts the workflow declares the right shape, parsing the
    matrix rather than substring-matching so explanatory comments don't sway
    it."""
    import yaml

    release_yml = _REPO / ".github" / "workflows" / "release.yml"
    assert release_yml.exists(), ".github/workflows/release.yml is required by the release scenario"
    text = release_yml.read_text()
    workflow = yaml.safe_load(text)
    legs = workflow["jobs"]["bundle"]["strategy"]["matrix"]["include"]
    triples = {leg["triple"] for leg in legs}
    assert triples == {"aarch64-apple-darwin", "x86_64-unknown-linux-gnu"}, (
        "release.yml matrix must build exactly macOS arm64 + Linux x64 "
        f"(no Intel macOS, no Windows); got {sorted(triples)}"
    )
    # SHA-256 checksums next to each artifact
    assert "sha256" in text.lower() or "shasum" in text.lower(), (
        "release.yml must emit SHA-256 checksums alongside artifacts"
    )


# ---------------------------------------------------------------------------
# CLI-only download tier
# ---------------------------------------------------------------------------


def _release_yml_text() -> str:
    return (_REPO / ".github" / "workflows" / "release.yml").read_text()


def test_release_workflow_packages_cli_only_archive() -> None:
    """The release workflow must produce a CLI-only download tier: an archive
    bundling just the coffer-daemon + coffer-mcp-shim sidecars, named
    coffer-cli-<triple>.tar.gz (macOS + Linux only — no Windows .zip). This is
    the standalone alternative to the desktop installers."""
    text = _release_yml_text()
    assert "coffer-cli-" in text, (
        "release.yml must package a CLI-only archive named coffer-cli-<triple>.*"
    )
    assert (
        "coffer-cli-${triple}.tar.gz" in text or "coffer-cli-${{ matrix.triple }}.tar.gz" in text
    ), "release.yml must produce a coffer-cli tar.gz on macOS/Linux"
    # Both sidecars must go into the CLI archive.
    assert "coffer-daemon-${triple}" in text, "CLI archive must include coffer-daemon"
    assert "coffer-mcp-shim-${triple}" in text, "CLI archive must include coffer-mcp-shim"


def test_release_workflow_checksums_cover_cli_archive() -> None:
    """The CLI archive must be checksummed like every other artifact. The
    SHA256SUMS step hashes all files in artifacts/, and the CLI archive is
    written into artifacts/, so it is covered. Assert the archive lands in
    artifacts/ and the checksum step runs over that directory."""
    text = _release_yml_text()
    assert "artifacts/$archive" in text or "artifacts/coffer-cli" in text, (
        "CLI archive must be written into artifacts/ so SHA256SUMS covers it"
    )
    assert "SHA256SUMS" in text, "release.yml must emit a SHA256SUMS file"


# ---------------------------------------------------------------------------
# Release-pipeline invariants (re-added after test_fix_validation.py removal)
# ---------------------------------------------------------------------------


def test_release_workflow_fails_on_empty_uploads() -> None:
    """A silent empty upload has masked broken bundle steps before — the
    upload step must set if-no-files-found: error so a zero-file match reds
    the workflow."""
    text = _release_yml_text()
    assert "if-no-files-found: error" in text, (
        "release.yml upload step must set if-no-files-found: error"
    )


def test_release_workflow_does_not_swallow_errors() -> None:
    """`2>/dev/null || true` patterns hide real failures (a missing bundle,
    a broken checksum). The release pipeline must surface errors, not mute
    them."""
    text = _release_yml_text()
    assert "2>/dev/null || true" not in text, (
        "release.yml must not swallow command failures with `2>/dev/null || true`"
    )


def test_release_workflow_does_not_reference_apple_secrets() -> None:
    """macOS signing/notarization is intentionally not wired. A disabled step
    that NAMES secrets.APPLE_* still surfaces them in repo-secret audits and
    security tooling, so the workflow must not reference them at all until a
    dedicated signed-release workflow is added."""
    text = _release_yml_text()
    assert "secrets.APPLE_CERTIFICATE" not in text, (
        "release.yml must not reference secrets.APPLE_CERTIFICATE"
    )
    assert "secrets.APPLE_ID" not in text, "release.yml must not reference secrets.APPLE_ID"


def test_release_workflow_marks_macos_artifacts_unsigned() -> None:
    """Until Apple signing is wired, macOS artifacts must carry a -unsigned
    marker so downloaders are not misled into thinking they're notarized."""
    text = _release_yml_text()
    assert "-unsigned" in text, "release.yml must mark macOS artifacts with a -unsigned suffix"


def test_release_workflow_runs_smoke_test() -> None:
    """The post-build smoke-test acceptance scenario must actually execute in
    CI: a step must invoke scripts/smoke_test_bundle.sh on the (macOS + Linux)
    matrix legs."""
    text = _release_yml_text()
    assert "scripts/smoke_test_bundle.sh" in text, (
        "release.yml must invoke scripts/smoke_test_bundle.sh after the bundle is built"
    )


def test_release_workflow_smoke_test_runs_on_all_legs() -> None:
    """With Windows dropped, the matrix is macOS + Linux only, so the smoke
    test runs on every leg and needs no Windows guard. It must also stay
    portable: `timeout` is GNU coreutils (absent on macOS), so neither the
    smoke-test step nor the script may depend on it — a regression that
    previously failed the macOS leg outright."""
    import yaml

    workflow = yaml.safe_load(_release_yml_text())
    steps = workflow["jobs"]["bundle"]["steps"]
    smoke_steps = [
        s
        for s in steps
        if isinstance(s.get("run"), str) and "scripts/smoke_test_bundle.sh" in s["run"]
    ]
    assert smoke_steps, "release.yml must have a step that runs scripts/smoke_test_bundle.sh"
    # No Windows leg remains, so the smoke step needs no windows `if:` guard.
    for step in smoke_steps:
        guard = str(step.get("if", "")).lower()
        assert "windows" not in guard, (
            "the matrix no longer includes Windows; the smoke-test step should "
            f"not carry a windows `if:` guard. got if={guard!r}"
        )
    # Portability regression guard: the smoke script must not call `timeout`.
    smoke_script = (_REPO / "scripts" / "smoke_test_bundle.sh").read_text()
    assert not re.search(r"(?<![\w-])timeout\s+\d", smoke_script), (
        "smoke_test_bundle.sh must not use the GNU `timeout` command "
        "(absent on macOS); use a backgrounded watchdog instead"
    )


@pytest.mark.acceptance(
    spec="003-mcp-gateway-desktop",
    scenario="post-build smoke test boots shim and gets JSON-RPC reply",
)
def test_smoke_test_bundle_script_present_and_invokes_shim() -> None:
    """scripts/smoke_test_bundle.sh runs against a freshly built bundle and
    asserts the bundled shim returns a JSON-RPC reply. We don't run it here
    by default (it needs a real installed bundle and platform-specific
    layouts); we just assert the script exists, is executable on POSIX,
    targets the shim, and speaks JSON-RPC initialize. Set COFFER_RUN_SMOKE=1
    + COFFER_SMOKE_BUNDLE=<path> to actually invoke it."""
    script = _REPO / "scripts" / "smoke_test_bundle.sh"
    assert script.exists(), "scripts/smoke_test_bundle.sh is required by the smoke-test scenario"
    contents = script.read_text()
    assert "coffer-mcp-shim" in contents, "smoke_test_bundle.sh must locate and run coffer-mcp-shim"
    assert '"initialize"' in contents or "'initialize'" in contents or "initialize" in contents, (
        "smoke_test_bundle.sh must send a JSON-RPC initialize request"
    )
    assert "jsonrpc" in contents.lower(), "smoke_test_bundle.sh must speak JSON-RPC"
    # The shim only replies after reaching a live daemon, and its frozen-binary
    # auto-spawn fallback can't relaunch itself — so the script must start the
    # bundled coffer-daemon itself and wait for it to listen.
    assert "coffer-daemon" in contents, (
        "smoke_test_bundle.sh must locate and start the bundled coffer-daemon"
    )
    assert "daemon/status" in contents, (
        "smoke_test_bundle.sh must wait for the daemon's /daemon/status before running the shim"
    )
    # The shim emits spaced JSON (json.dumps default separators) so the reply
    # checks must be whitespace-tolerant. The grep lines that validate the
    # reply must NOT use the compact no-space literal the spaced output never
    # produces; they must use a [[:space:]]-tolerant pattern instead.
    grep_lines = [ln for ln in contents.splitlines() if "grep" in ln and "REPLY" in ln]
    assert grep_lines, "smoke_test_bundle.sh must grep the shim REPLY for validation"
    for ln in grep_lines:
        assert '"jsonrpc":"2.0"' not in ln and '"id":1' not in ln, (
            f"smoke_test_bundle.sh validates the reply with a compact literal that "
            f"the spaced json.dumps output never matches: {ln.strip()}"
        )
    assert any("[[:space:]]" in ln for ln in grep_lines), (
        "smoke_test_bundle.sh must use whitespace-tolerant matching for the JSON-RPC reply"
    )

    if os.environ.get("COFFER_RUN_SMOKE") != "1":
        pytest.skip("set COFFER_RUN_SMOKE=1 + COFFER_SMOKE_BUNDLE=<path> to invoke the script")

    bundle = os.environ.get("COFFER_SMOKE_BUNDLE")
    if not bundle:
        pytest.skip("COFFER_RUN_SMOKE=1 set but COFFER_SMOKE_BUNDLE=<bundle-path> missing")

    result = subprocess.run(
        ["bash", str(script), bundle],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"smoke_test_bundle.sh failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
