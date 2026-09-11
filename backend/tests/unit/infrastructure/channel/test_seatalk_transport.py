"""The SeaTalk transport's error reporting.

A rejection reaches the rest of Coffer as a ``ChannelSendFailed`` message, and
whatever is not in that string is lost — so what the string carries is the
whole of what a future debugger has to work with.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.channel.seatalk_transport import _detail


class TestRejectionDetail:
    """A refusal must carry the platform's own explanation.

    `code=102` alone covers everything from an over-long card to a malformed
    body; we chased two separate failures blind because the envelope's message
    was dropped at the raise site.
    """

    def test_the_platform_message_is_appended(self) -> None:
        assert _detail({"code": 102, "message": "invalid element count"}) == (
            " message='invalid element count'"
        )

    def test_other_key_names_are_tried(self) -> None:
        assert _detail({"code": 102, "error_msg": "bad param"}) == " error_msg='bad param'"

    def test_an_envelope_with_no_message_still_reports_what_it_carried(self) -> None:
        assert _detail({"code": 102, "request_id": "x", "field": "employee_code"}) == (
            " payload={'field': 'employee_code'}"
        )

    def test_a_bare_envelope_adds_nothing(self) -> None:
        assert _detail({"code": 102, "request_id": "x"}) == ""

    def test_a_non_dict_payload_adds_nothing(self) -> None:
        assert _detail(["nope"]) == ""


class TestStreamCadence:
    """How often a stream may write, and why it is tunable.

    The client replaces the text with each snapshot rather than animating
    towards it, so update frequency IS the typewriter effect. The default is a
    judgement against an undocumented allowance, so it has to be adjustable
    without a rebuild.
    """

    def test_the_default_is_finer_than_seatalks_suggested_buffer(self) -> None:
        # Measured: deltas arrive ~25 ms apart carrying ~4 characters. At the
        # suggested 200 ms that is ~30 characters a jump — a sentence at a time.
        import importlib

        from coffer.infrastructure.channel import live_text

        assert live_text.MIN_UPDATE_INTERVAL <= 0.1
        assert importlib  # keeps the import meaningful to a reader

    def test_the_interval_can_be_retuned_without_a_rebuild(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib

        from coffer.infrastructure.channel import live_text

        monkeypatch.setenv("COFFER_SEATALK_STREAM_INTERVAL", "0.35")
        reloaded = importlib.reload(live_text)
        try:
            assert reloaded.MIN_UPDATE_INTERVAL == 0.35
        finally:
            monkeypatch.delenv("COFFER_SEATALK_STREAM_INTERVAL")
            importlib.reload(live_text)
