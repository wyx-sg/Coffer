"""Static checks on the PyInstaller specs and the release packaging.

Does NOT actually build binaries — that's done by `make bundle-binaries`
and (in CI) the cross-platform GitHub Actions matrix. These tests just
verify the configuration files are present + structurally correct, so
broken wiring is caught early.
"""

from __future__ import annotations

import ast
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


def _collect_data_files_args(tree: ast.AST) -> set[str]:
    """Return the first-positional-arg string for every collect_data_files() call."""
    args: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "collect_data_files"
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
        ("coffer-callback.spec", "coffer/surfaces/callback/__main__.py"),
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


def test_build_script_present_and_executable() -> None:
    script = _REPO / "scripts" / "build_binaries.sh"
    assert script.exists(), "scripts/build_binaries.sh missing"
    # Must be readable
    contents = script.read_text()
    assert "pyinstaller" in contents.lower()
    assert "dist/" in contents


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
# Release packaging
# ---------------------------------------------------------------------------


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

    # The build runs pyinstaller from backend/ (build_binaries.sh), so
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


def test_daemon_spec_ships_no_vector_engine() -> None:
    """The daemon spec MUST NOT bundle sqlite-vec.

    It used to, so the frozen build could load the vec0 extension behind vector
    retrieval. There is no vector retrieval and no index at all any more (ADR
    knowledge-is-plain-files), and the package is gone from the dependency set —
    so collecting it would bundle a native extension nothing can load."""
    tree = _parse_spec(_REPO / "backend" / "coffer-daemon.spec")
    assert "sqlite_vec" not in _collect_data_files_args(tree)
    assert "sqlite_vec" not in _collect_submodules_args(tree)


def test_daemon_spec_includes_attachment_and_chat_hidden_imports() -> None:
    """The hidden-imports list predates the knowledge base, memory and
    channel-attachment and agent-chat features, whose runtime deps are imported
    LAZILY (inside functions) so PyInstaller's static analysis misses them.
    Declare them explicitly so a frozen daemon can extract an inbound
    attachment and drive the built-in chat agent.

    Each of these is a real lazy importer in the codebase:
      * markitdown  — infrastructure/chat/document_extract.py (spec channels FR-030)
      * openai      — infrastructure/provider/*
      * langgraph / langchain — infrastructure/llm/*, infrastructure/chat/*

    The knowledge layer declares nothing here: it is a directory of markdown
    files with no converter, no index and no embedding client to bundle.

    MarkItDown goes one level deeper: it imports its format backends lazily
    *inside* each converter. PyInstaller's graph may trace them transitively, but
    we collect the readers behind the markitdown[docx,pdf,pptx,xls,xlsx] extras
    explicitly (belt-and-suspenders) so a build that fails to trace them still
    ships working converters instead of raising MissingDependencyException on
    PDF/office uploads.
    """
    tree = _parse_spec(_REPO / "backend" / "coffer-daemon.spec")
    submodules = _collect_submodules_args(tree)
    for pkg in ("markitdown", "openai", "langgraph", "langchain"):
        assert pkg in submodules, (
            f"daemon spec must collect_submodules({pkg!r}) — it is imported "
            "lazily by chat/provider code and PyInstaller misses it statically"
        )
    for pkg in ("pdfminer", "pdfplumber", "pptx", "mammoth", "openpyxl", "xlrd"):
        assert pkg in submodules, (
            f"daemon spec must collect_submodules({pkg!r}) — MarkItDown imports it "
            "lazily to read a format an inbound attachment may arrive in"
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
    spec="mcp-gateway",
    scenario="release tag produces the CLI archive and SHA256SUMS",
)
def test_release_workflow_produces_platform_artifact_matrix() -> None:
    """The release workflow must define a matrix that produces the supported
    platform — macOS arm64 (Apple Silicon) — and ship a SHA-256 checksum
    alongside each installer. macOS x64 (Intel), Linux, and Windows are
    intentionally NOT built: Intel runners are deprecated/starved, PyInstaller
    can't cross-compile, and the Linux/Windows legs were never validated
    end-to-end. The actual build runs in CI on tag push; this asserts the
    workflow declares the right shape, parsing the matrix rather than
    substring-matching so explanatory comments don't sway it."""
    import yaml

    release_yml = _REPO / ".github" / "workflows" / "release.yml"
    assert release_yml.exists(), ".github/workflows/release.yml is required by the release scenario"
    text = release_yml.read_text()
    workflow = yaml.safe_load(text)
    legs = workflow["jobs"]["bundle"]["strategy"]["matrix"]["include"]
    triples = {leg["triple"] for leg in legs}
    assert triples == {"aarch64-apple-darwin"}, (
        "release.yml matrix must build exactly macOS arm64 "
        f"(no Intel macOS, no Linux, no Windows); got {sorted(triples)}"
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


def test_release_workflow_packages_the_cli_archive() -> None:
    """The CLI download tier: coffer-cli-<triple>.tar.gz.

    Every binary the daemon resolves at runtime must be inside it. The daemon
    deploys `coffer-mcp-shim` and `coffer-callback` out of its
    own directory (spec mcp-gateway FR-026) and finds `coffer-daemon` as a sibling
    (ADR daemon-detect-or-spawn), so an archive missing any of them ships a build whose helper
    processes cannot start.
    """
    text = _release_yml_text()
    assert (
        "coffer-cli-${triple}.tar.gz" in text or "coffer-cli-${{ matrix.triple }}.tar.gz" in text
    ), "release.yml must produce a coffer-cli-<triple>.tar.gz"
    for binary in (
        "coffer-daemon",
        "coffer-mcp-shim",
        "coffer-callback",
    ):
        assert binary in text, f"CLI archive must include {binary}"


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="release tag produces the CLI archive and SHA256SUMS",
)
def test_release_workflow_packages_the_desktop_dmg_tier() -> None:
    """The SECOND download tier: the desktop app, as an unsigned .dmg.

    Nothing asserted this, which is how a scenario claiming "exactly one
    download tier and no desktop bundle" stayed green for every release that
    shipped a .dmg. The desktop shell is back (PR restoring it, and
    ``desktop/tauri.conf.json`` targets ``app``/``dmg``), so the release has
    two tiers and the test says so.

    ``unsigned`` is asserted deliberately, not incidentally: there is no
    Developer ID yet, and the filename is where a downloader learns that
    before Gatekeeper tells them.
    """
    text = _release_yml_text()
    assert "Coffer-unsigned-${triple}.dmg" in text or (
        "Coffer-unsigned-${{ matrix.triple }}.dmg" in text
    ), "release.yml must collect the desktop app as Coffer-unsigned-<triple>.dmg"
    assert "bundle/dmg" in text, (
        "release.yml must collect the .dmg out of the Tauri bundle directory"
    )
    # "…and no third tier": the scenario's Then bounds the release at two, so
    # the packagings that were tried and dropped must not creep back in
    # unnoticed. `.app.zip` in particular shipped alongside the .dmg once.
    for third_tier in (".app.zip", ".pkg", ".deb", ".msi", ".appimage"):
        assert third_tier not in text.lower(), (
            f"release.yml packages a third download tier ({third_tier}); the "
            "release is the CLI archive and the .dmg, and nothing else"
        )


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="release tag produces the CLI archive and SHA256SUMS",
)
def test_release_workflow_checksums_cover_both_tiers() -> None:
    """Both tiers must be checksummed like every other artifact. The SHA256SUMS
    step hashes all files in artifacts/, so the assertion is that each tier
    lands in artifacts/ and the checksum step runs over that directory."""
    text = _release_yml_text()
    assert "artifacts/$archive" in text or "artifacts/coffer-cli" in text, (
        "CLI archive must be written into artifacts/ so SHA256SUMS covers it"
    )
    assert "artifacts/Coffer-unsigned-" in text, (
        "the .dmg must be written into artifacts/ so SHA256SUMS covers it"
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


def test_release_workflow_tells_downloaders_the_build_is_unsigned() -> None:
    """Until Apple signing is wired, the release must say so.

    The `-unsigned` filename suffix went with the .dmg and .app.zip the
    desktop shell produced; a tar.gz of CLI binaries never carried it. The
    obligation it encoded — do not let a downloader assume this is notarised —
    now rides in the release notes, together with the quarantine command they
    will otherwise have to search for.
    """
    text = _release_yml_text()
    assert "unsigned" in text.lower(), "release notes must state that macOS builds are unsigned"
    assert "com.apple.quarantine" in text, (
        "release notes must tell macOS users how to clear the quarantine flag"
    )


def test_release_workflow_runs_smoke_test() -> None:
    """The post-build smoke-test acceptance scenario must actually execute in
    CI: a step must invoke scripts/smoke_test_bundle.sh on the macOS matrix
    leg."""
    text = _release_yml_text()
    assert "scripts/smoke_test_bundle.sh" in text, (
        "release.yml must invoke scripts/smoke_test_bundle.sh after the bundle is built"
    )


def test_release_workflow_smoke_test_runs_on_all_legs() -> None:
    """With Linux and Windows dropped, the matrix is macOS only, so the smoke
    test runs on every leg and needs no platform guard. It must also stay
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
    spec="mcp-gateway",
    scenario="release tag produces the CLI archive and SHA256SUMS",
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


def test_release_workflow_publishes_the_desktop_tier() -> None:
    """The release produces a second tier beside the CLI archive: the `.dmg`.

    Restoring the desktop shell put a self-contained app back in the release
    (spec mcp-gateway FR-022, ADR desktop-shell-over-a-shared-frontend). Every
    invariant that tier depends on is a filename or a path, none of which any
    other test pins, and the feedback loop for getting one wrong is a tagged
    release — the same reason the CLI tier is pinned here.
    """
    text = _release_yml_text()

    assert "desktop/binaries/" in text, (
        "release.yml must stage the frozen binaries where tauri.conf.json's "
        "externalBin looks for them"
    )
    assert "@tauri-apps/cli" in text, "release.yml must run the Tauri build for the desktop tier"
    # Comments are excluded deliberately: the workflow explains in prose why it
    # does NOT cargo-install the CLI, and matching that sentence would make this
    # assertion fire on the very documentation that agrees with it.
    executable = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "cargo install tauri-cli" not in executable, (
        "the Tauri CLI must come from npm; compiling it from source on every "
        "cold cache costs minutes to produce a tool invoked once"
    )
    assert ".dmg" in text, "release.yml must collect a .dmg"


def test_desktop_tier_reuses_the_already_frozen_binaries() -> None:
    """The desktop leg must copy out of `dist/`, not freeze a second time.

    PyInstaller over four binaries is the expensive half of the release and the
    CLI leg has already done it. A second run would roughly double the job's
    wall clock for artifacts that are byte-identical, and — worse — could ship
    an app whose binaries were built from a different invocation than the
    archive's.
    """
    text = _release_yml_text()
    staging = [ln for ln in text.splitlines() if "desktop/binaries/" in ln and "cp " in ln]
    assert staging, "release.yml must copy the frozen binaries into desktop/binaries/"
    for line in staging:
        assert "dist/" in line, (
            f"the desktop tier must stage out of dist/ (the CLI leg's output), not "
            f"rebuild: {line.strip()}"
        )
    # Count invocations, not mentions. The workflow names the script in several
    # comments explaining what it staged where, and once inside an `echo` that
    # reports a missing output; none of those is a second freeze.
    invocations = [
        ln
        for ln in text.splitlines()
        if "bash scripts/build_binaries.sh" in ln
        and not ln.lstrip().startswith("#")
        and "echo" not in ln
    ]
    assert len(invocations) == 1, (
        f"build_binaries.sh must run exactly once per release leg — a second "
        f"invocation for the desktop tier is the duplicate freeze this guards; "
        f"found {len(invocations)}: {invocations}"
    )


def test_desktop_and_backend_versions_are_the_same_string() -> None:
    """The shell's version and the daemon's must match, exactly.

    `daemon_version_matches` (desktop/src/daemon.rs) compares the Rust crate's
    CARGO_PKG_VERSION against the version `/api/v1/daemon/status` reports, which
    is the Python package's, by string equality. Bump one without the other and
    every desktop launch shows "daemon out of date — restart it" permanently:
    the restart the banner offers cannot fix a mismatch that is baked into the
    two builds. `tauri.conf.json` carries a third copy, which names the `.dmg`.
    """

    def _version(path: Path, pattern: str) -> str:
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        assert match, f"no version found in {path}"
        return match.group(1)

    backend_version = _version(_REPO / "backend" / "pyproject.toml", r'^version = "([^"]+)"')
    cargo_version = _version(_REPO / "desktop" / "Cargo.toml", r'^version = "([^"]+)"')
    tauri_version = _version(_REPO / "desktop" / "tauri.conf.json", r'"version"\s*:\s*"([^"]+)"')

    assert cargo_version == backend_version, (
        f"desktop/Cargo.toml is {cargo_version} but backend/pyproject.toml is "
        f"{backend_version} — the desktop app would report permanent version skew"
    )
    assert tauri_version == backend_version, (
        f"desktop/tauri.conf.json is {tauri_version} but backend/pyproject.toml is "
        f"{backend_version} — the .dmg would be named for the wrong version"
    )
    # The frontend's package.json is the fourth copy: the SPA the daemon serves
    # is built from it, and a bump that misses it ships a UI labelled with the
    # previous release.
    frontend_version = _version(
        _REPO / "frontend" / "package.json", r'^  "version"\s*:\s*"([^"]+)"'
    )
    assert frontend_version == backend_version, (
        f"frontend/package.json is {frontend_version} but backend/pyproject.toml is "
        f"{backend_version} — run scripts/bump_version.py to move them together"
    )


_BUMP_TARGETS = (
    "backend/pyproject.toml",
    "frontend/package.json",
    "frontend/package-lock.json",
    "desktop/Cargo.toml",
    "desktop/Cargo.lock",
    "desktop/tauri.conf.json",
)


def _copy_version_files(dest: Path) -> None:
    for rel in _BUMP_TARGETS:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((_REPO / rel).read_text(encoding="utf-8"), encoding="utf-8")


def _run_bump(root: Path, version: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "bump_version.py"), version, "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_bump_version_moves_every_copy_together(tmp_path: Path) -> None:
    """`scripts/bump_version.py` rewrites all six files, and only the version
    anchors in them — the dependency pins that also say `version` are untouched."""
    _copy_version_files(tmp_path)
    before = {rel: (tmp_path / rel).read_text(encoding="utf-8") for rel in _BUMP_TARGETS}

    result = _run_bump(tmp_path, "9.8.7")
    assert result.returncode == 0, result.stderr

    patterns = {
        "backend/pyproject.toml": r'^version = "9\.8\.7"$',
        "frontend/package.json": r'^  "version": "9\.8\.7",$',
        "frontend/package-lock.json": r'^  "version": "9\.8\.7",$',
        "desktop/Cargo.toml": r'^version = "9\.8\.7"$',
        "desktop/Cargo.lock": r'^name = "coffer-desktop"\nversion = "9\.8\.7"$',
        "desktop/tauri.conf.json": r'^  "version": "9\.8\.7",$',
    }
    for rel, pattern in patterns.items():
        after = (tmp_path / rel).read_text(encoding="utf-8")
        assert re.search(pattern, after, re.MULTILINE), f"{rel} not bumped:\n{after[:400]}"
        # Exactly the version anchors changed: the diff is a handful of lines,
        # never a reformatted file or a dependency's own version line.
        changed = [
            (a, b)
            for a, b in zip(before[rel].splitlines(), after.splitlines(), strict=True)
            if a != b
        ]
        assert 1 <= len(changed) <= 2, f"{rel}: unexpected lines changed: {changed}"
        assert all("9.8.7" in b for _, b in changed), changed
    # The lockfile's root package entry moved too (its second copy of the version).
    lock = (tmp_path / "frontend/package-lock.json").read_text(encoding="utf-8")
    assert lock.count('"version": "9.8.7"') == 2


def test_bump_version_rejects_a_malformed_version_and_writes_nothing(tmp_path: Path) -> None:
    _copy_version_files(tmp_path)
    before = {rel: (tmp_path / rel).read_text(encoding="utf-8") for rel in _BUMP_TARGETS}

    result = _run_bump(tmp_path, "not-a-version")

    assert result.returncode != 0
    assert "not a version" in result.stderr
    assert {rel: (tmp_path / rel).read_text(encoding="utf-8") for rel in _BUMP_TARGETS} == before


def test_bump_version_leaves_all_files_untouched_when_one_anchor_is_missing(
    tmp_path: Path,
) -> None:
    """All-or-nothing: a file whose anchor moved must not leave the others bumped."""
    _copy_version_files(tmp_path)
    (tmp_path / "desktop/Cargo.lock").write_text("# no package entries\n", encoding="utf-8")
    before = {rel: (tmp_path / rel).read_text(encoding="utf-8") for rel in _BUMP_TARGETS}

    result = _run_bump(tmp_path, "9.8.7")

    assert result.returncode != 0
    assert "Cargo.lock" in result.stderr
    assert {rel: (tmp_path / rel).read_text(encoding="utf-8") for rel in _BUMP_TARGETS} == before
