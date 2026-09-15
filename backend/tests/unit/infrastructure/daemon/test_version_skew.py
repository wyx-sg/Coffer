"""Cross-build attachment is reported, never refused (ADR daemon-detect-or-spawn)."""

from __future__ import annotations

from coffer.infrastructure.daemon.version_skew import skew_warning


def test_same_version_is_silent() -> None:
    assert skew_warning({"version": "1.2.3"}, caller="coffer", caller_version="1.2.3") is None


def test_different_version_names_both_builds_and_the_daemon_executable() -> None:
    message = skew_warning(
        {"version": "1.2.3", "executable": "/old/coffer-daemon"},
        caller="coffer-mcp-shim",
        caller_version="1.3.0",
    )
    assert message is not None
    assert message.startswith("coffer-mcp-shim: WARNING:")
    assert "1.2.3" in message and "1.3.0" in message
    assert "/old/coffer-daemon" in message
    assert "coffer daemon restart" in message
    assert "\n" not in message


def test_missing_executable_is_omitted_not_rendered_as_none() -> None:
    message = skew_warning({"version": "1.2.3"}, caller="coffer", caller_version="1.3.0")
    assert message is not None
    assert "None" not in message and "()" not in message


def test_unknown_status_cannot_be_a_mismatch() -> None:
    """An older daemon without the field, or an unparsable body, reads as
    "cannot tell" — a warning must never fire on missing evidence."""
    assert skew_warning(None, caller="coffer", caller_version="1.3.0") is None
    assert skew_warning({}, caller="coffer", caller_version="1.3.0") is None
    assert skew_warning({"version": 7}, caller="coffer", caller_version="1.3.0") is None


def test_default_caller_version_is_this_build() -> None:
    import coffer

    assert skew_warning({"version": coffer.__version__}, caller="coffer") is None
    assert skew_warning({"version": "0.0.0-not-us"}, caller="coffer") is not None
