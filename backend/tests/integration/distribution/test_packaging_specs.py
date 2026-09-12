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
      * openai      — infrastructure/providers/*
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


def test_release_workflow_packages_the_single_cli_archive() -> None:
    """The release produces exactly one download tier: coffer-cli-<triple>.tar.gz.

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

    # A frozen build that drops sqlite-vec's vec0 extension silently degrades
    # vector retrieval to keyword-only (VecIndex.available() swallows the load
    # failure). The smoke test must probe vec availability against the bundled
    # daemon so that regression reds the build instead of shipping quietly.
    assert "vec" in contents.lower() and "available" in contents.lower(), (
        "smoke_test_bundle.sh must probe sqlite-vec availability so a frozen "
        "build that lost the vec0 extension fails the smoke test"
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
