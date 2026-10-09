"""The SeaTalk transport's error reporting.

A rejection reaches the rest of Coffer as a ``ChannelSendFailed`` message, and
whatever is not in that string is lost — so what the string carries is the
whole of what a future debugger has to work with.
"""

from __future__ import annotations

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
