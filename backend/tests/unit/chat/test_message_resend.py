"""Sending a persisted user message again — the page's Retry (spec chat "Show a
failed turn as one inline banner with Retry").

The retry is rebuilt from the persisted row, so it carries the original's
attachment references; a file the media sweep has since deleted refuses the
retry instead of sending it without the file.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from coffer.application.chat.attachments import ChatAttachmentService
from coffer.domain.chat.errors import AttachmentExpired, MessageNotFound
from coffer.domain.chat.message import AttachmentBlock, Role, TextBlock
from tests.unit.chat.conftest import FakeChatMediaStore, make_chat_services, make_message

_SHOT = AttachmentBlock(path="/media/a1.png", mime="image/png", filename="shot.png")
_NOTES = AttachmentBlock(path="/media/b2.md", mime="text/markdown", filename="notes.md")


async def test_reattach_returns_the_text_and_every_reference_in_order() -> None:
    message = replace(
        make_message(0, "what is in these?"),
        content=[TextBlock(text="what is in these?"), _SHOT, _NOTES],
    )
    text, attachments = await ChatAttachmentService(FakeChatMediaStore()).reattach(message)

    assert text == "what is in these?"
    assert [(a.path, a.mime, a.filename) for a in attachments] == [
        ("/media/a1.png", "image/png", "shot.png"),
        ("/media/b2.md", "text/markdown", "notes.md"),
    ]


async def test_reattach_refuses_a_reference_whose_file_was_swept() -> None:
    store = FakeChatMediaStore()
    store.gone.add(_NOTES.path)
    message = replace(make_message(0, "look"), content=[TextBlock(text="look"), _SHOT, _NOTES])

    with pytest.raises(AttachmentExpired) as exc:
        await ChatAttachmentService(store).reattach(message)

    assert exc.value.code == "ATTACHMENT_EXPIRED"
    assert exc.value.filename == "notes.md"
    assert "notes.md" in str(exc.value)


async def test_get_user_message_finds_only_a_user_row_of_that_conversation() -> None:
    chat_svc, _orchestrator, _registry = make_chat_services()
    conv = await chat_svc.create_conversation(agent_key="builtin")
    user = await chat_svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="hi")])
    reply = await chat_svc.append_message(
        conv.id, role=Role.ASSISTANT, content=[TextBlock(text="hello")]
    )

    assert (await chat_svc.get_user_message(conv.id, user.id)).id == user.id
    with pytest.raises(MessageNotFound):
        await chat_svc.get_user_message(conv.id, reply.id)
    with pytest.raises(MessageNotFound):
        await chat_svc.get_user_message(conv.id, "nope")
