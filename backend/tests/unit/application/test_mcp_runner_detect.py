"""Missing-runner detection (spec 001 amendment)."""

from __future__ import annotations

from coffer.application.mcp.runner_detect import missing_runner


def test_missing_runner_detection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A resolvable command (sh is everywhere) is not missing.
    assert missing_runner("sh") is None
    # A bare name not on PATH reports its basename.
    assert missing_runner("definitely-not-a-real-runner-xyz") == "definitely-not-a-real-runner-xyz"
    # Absolute paths check existence directly.
    existing = tmp_path / "tool"
    existing.write_text("#!/bin/sh\n")
    assert missing_runner(str(existing)) is None
    assert missing_runner(str(tmp_path / "gone")) == "gone"
    assert missing_runner("") is None
