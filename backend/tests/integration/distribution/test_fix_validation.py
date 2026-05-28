"""Static fix-validation tests for PR #24 distribution / packaging findings."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_WORKFLOW = _REPO / ".github" / "workflows" / "release.yml"
_BUILD_SH = _REPO / "scripts" / "build_binaries.sh"
_SMOKE_SH = _REPO / "scripts" / "smoke_test_bundle.sh"


def _release_yml() -> str:
    return _WORKFLOW.read_text()


def test_release_yml_no_silent_cp_failures() -> None:
    """CODE24-014: cp failures during artifact collection must NOT be swallowed."""
    content = _release_yml()
    # The old pattern is `cp ... 2>/dev/null || true` — both halves of that
    # idiom are signal-suppressing.
    assert "2>/dev/null || true" not in content, (
        "release.yml must not swallow cp errors in artifact-collect steps"
    )


def test_release_yml_upload_fails_on_empty() -> None:
    """CODE24-014: upload-artifact must error (not warn) on zero matches."""
    content = _release_yml()
    assert "if-no-files-found: error" in content, (
        "upload-artifact step must use if-no-files-found: error"
    )
    assert "if-no-files-found: warn" not in content, (
        "upload-artifact must not fall back to warn (silent CI rot)"
    )


def test_release_yml_no_apple_secret_references_in_disabled_step() -> None:
    """CODE24-021: don't list APPLE_* secrets in a step gated on `if: false`.

    Secret references in dead steps still surface in repo-secret audits and
    confuse readers about which secrets are actually consumed. The fix
    removes the entire dead step; the doc-comment is the new placeholder.
    """
    content = _release_yml()
    assert "secrets.APPLE_CERTIFICATE" not in content, (
        "release.yml must not reference APPLE_CERTIFICATE inside a disabled step"
    )
    assert "secrets.APPLE_ID" not in content, (
        "release.yml must not reference APPLE_ID inside a disabled step"
    )


def test_release_yml_macos_artifacts_tagged_unsigned() -> None:
    """CODE24-020: macOS bundles are unsigned until APPLE_* is wired."""
    content = _release_yml()
    assert "-unsigned" in content, (
        "macOS artifact names must include a -unsigned suffix while "
        "code-signing/notarization are disabled"
    )


def test_build_binaries_handles_cygwin_and_arm64_windows() -> None:
    """CODE24-017: widen Windows triple detection."""
    content = _BUILD_SH.read_text()
    assert "CYGWIN" in content, "build_binaries.sh must recognise CYGWIN_NT"
    assert "aarch64-pc-windows-msvc" in content, (
        "build_binaries.sh must map ARM64 Windows to aarch64-pc-windows-msvc"
    )


def test_smoke_test_uses_mktemp_for_stderr() -> None:
    """CODE24-016: don't use a predictable /tmp path for stderr capture."""
    content = _SMOKE_SH.read_text()
    assert "/tmp/smoke_shim_stderr" not in content, (
        "smoke_test_bundle.sh must not hard-code /tmp/smoke_shim_stderr"
    )
    assert "SMOKE_STDERR" in content and "mktemp" in content, (
        "smoke_test_bundle.sh must allocate stderr file via mktemp"
    )


def test_smoke_test_input_via_heredoc_not_single_quoted_bash_c() -> None:
    """CODE24-015: JSON payload was single-quoted inside `bash -c '…'` —

    breaks the second a literal apostrophe appears. Heredoc avoids that.
    """
    content = _SMOKE_SH.read_text()
    # The old form looked like: bash -c "printf '%s\n' '$INPUT' | timeout …"
    assert 'bash -c "printf' not in content, (
        "smoke_test_bundle.sh must not embed the JSON payload in a single-quoted bash -c string"
    )


@pytest.mark.parametrize(
    "needle",
    [
        "CSP notes",
        "connect-src",
        "style-src",
    ],
)
def test_build_rs_documents_csp_choices(needle: str) -> None:
    """CODE24-018 / CODE24-019: document why the CSP keeps wildcard loopback
    and 'unsafe-inline' styles."""
    content = (_REPO / "desktop" / "build.rs").read_text()
    assert needle in content, f"build.rs must document CSP rationale ({needle})"
