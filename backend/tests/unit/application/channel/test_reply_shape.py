"""Finding the ``## Details`` section of a finished reply (spec channels "Shape
a reply for what the chat can show")."""

from __future__ import annotations

from coffer.application.channel.reply_shape import split_details


def test_the_details_section_is_split_off_its_heading() -> None:
    head, details = split_details("Deploy is green.\n\n## Details\n\n- step one\n- step two")
    assert head == "Deploy is green."
    assert details == "- step one\n- step two"
    assert split_details("no details here") == ("no details here", "")
