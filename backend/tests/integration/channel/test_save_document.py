"""`/save`: the phone forwards a document into a knowledge collection (spec channels FR-014, spec
channels FR-031/FR-034).

The trigger is a plain TEXT `/save [collection]`, sent as its own message
after the document — never a caption. A caption starting with "/" alongside an
attachment is already a normal message, not a command (see ``inbound.py``);
`/save` does not carve out an exception to that, so it stays an ordinary
follow-up command like every other one, acting on the most recently received
attachment in this (channel, chat, thread) — the channel's own memory of "what
was just sent here", never a second copy of the bytes (those still live only
at the path the transport downloaded them to, read once, at save time, through
the ingest service).

The collection is always confirmed: a name that is both typed AND visible is
used outright (the owner already confirmed it by typing it); anything else
falls back to a selection card, reusing the same mechanism `/agent`/`/model`
already render — never a second one.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.domain.channel.envelopes import InboundAttachment

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, tap_event, wait_until


def _attach(
    tmp_path: Any, name: str = "note.txt", body: bytes = b"hello world"
) -> InboundAttachment:
    path = tmp_path / name
    path.write_bytes(body)
    return InboundAttachment(path=str(path), mime="text/plain", filename=name)


async def _send_document(
    env: ChannelEnv, adapter: FakeChannelAdapter, attachment: InboundAttachment, **kw: Any
) -> None:
    """Send the document and let its own (ordinary, unrelated) turn finish, so
    the background drain task never outlives the test — `/save` itself does
    not depend on this turn: the pending document is recorded synchronously,
    before the turn is even queued."""
    await env.processor.on_message(inbound("tg", "owner", "", attachments=[attachment], **kw))
    await wait_until(lambda: "Hello world" in adapter.texts())


async def _card_channel(env: ChannelEnv, *, sender_id: str = "owner-1") -> FakeChannelAdapter:
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=True)
    )
    await env.pair(resource, "owner", sender_id=sender_id)
    return adapter


@pytest.mark.acceptance(
    spec="channels", scenario="a document sent to a channel is saved into a collection"
)
async def test_named_existing_collection_saves_directly(env: ChannelEnv, tmp_path: Any) -> None:
    _resource, adapter = await env.paired_channel(sender_id="owner-1")
    env.collections.names = ["research"]
    attachment = _attach(tmp_path)

    await _send_document(env, adapter, attachment, sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "/save research", sender_id="owner-1"))

    assert len(env.ingest.calls) == 1
    call = env.ingest.calls[0]
    assert call["collection"] == "research"
    assert call["filename"] == "note.txt"
    assert call["data"] == b"hello world"
    assert call["actor"] == "user"
    assert call["agent"] == "builtin"  # the channel's default_agent
    # The confirmation names the title, the collection, and the path — never a
    # stack trace, and never silence.
    assert any("note.txt" in text and "research" in text for _chat, text in adapter.sent)


async def test_non_owner_message_stores_nothing(env: ChannelEnv, tmp_path: Any) -> None:
    """The owner gate is reused, not re-implemented: an attachment AND a
    `/save` from a chat-id match but sender-id mismatch are both refused
    silently — nothing is cached, nothing is ingested, nothing is said."""
    _resource, adapter = await env.paired_channel(sender_id="owner-1")
    attachment = _attach(tmp_path)

    await env.processor.on_message(
        inbound("tg", "owner", "", attachments=[attachment], sender_id="intruder")
    )
    await env.processor.on_message(inbound("tg", "owner", "/save", sender_id="intruder"))

    assert env.ingest.calls == []
    assert adapter.sent == []
    assert adapter.cards == []


async def test_save_with_nothing_pending_is_refused(env: ChannelEnv) -> None:
    await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(inbound("tg", "owner", "/save", sender_id="owner-1"))

    assert env.ingest.calls == []


@pytest.mark.acceptance(spec="channels", scenario="a save that names no collection asks which one")
async def test_unnamed_save_offers_a_card_even_for_a_single_collection(
    env: ChannelEnv, tmp_path: Any
) -> None:
    """FR-038: confirm, never guess — even a lone collection is offered as a
    tap, not applied automatically."""
    adapter = await _card_channel(env)
    env.collections.names = ["only-one"]
    attachment = _attach(tmp_path)

    await _send_document(env, adapter, attachment, sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "/save", sender_id="owner-1"))

    assert env.ingest.calls == []
    assert len(adapter.cards) == 1
    _chat, _text, buttons = adapter.cards[0]
    assert [b.value for b in buttons] == ["collection:only-one"]


async def test_unknown_named_collection_falls_back_to_a_card(
    env: ChannelEnv, tmp_path: Any
) -> None:
    adapter = await _card_channel(env)
    env.collections.names = ["research"]
    attachment = _attach(tmp_path)

    await _send_document(env, adapter, attachment, sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "/save nope", sender_id="owner-1"))

    assert env.ingest.calls == []
    assert len(adapter.cards) == 1
    assert any("Unknown collection" in text for _chat, text in adapter.sent)


async def test_unnamed_save_without_buttons_lists_collections_as_text(
    env: ChannelEnv, tmp_path: Any
) -> None:
    _resource, adapter = await env.paired_channel(sender_id="owner-1")
    env.collections.names = ["research", "recipes"]
    attachment = _attach(tmp_path)

    await _send_document(env, adapter, attachment, sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "/save", sender_id="owner-1"))

    assert env.ingest.calls == []
    assert adapter.cards == []
    [text] = [text for _chat, text in adapter.sent if "research" in text]
    assert "research" in text and "recipes" in text


async def test_no_collections_yet_says_so(env: ChannelEnv, tmp_path: Any) -> None:
    _resource, adapter = await env.paired_channel(sender_id="owner-1")
    attachment = _attach(tmp_path)

    await _send_document(env, adapter, attachment, sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "/save", sender_id="owner-1"))

    assert env.ingest.calls == []
    assert any("No collections yet" in text for _chat, text in adapter.sent)


async def test_collection_card_tap_saves_the_pending_document(
    env: ChannelEnv, tmp_path: Any
) -> None:
    adapter = await _card_channel(env)
    env.collections.names = ["research", "recipes"]
    attachment = _attach(tmp_path, name="scan.pdf", body=b"%PDF-fake")

    await _send_document(env, adapter, attachment, sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "/save", sender_id="owner-1"))
    assert len(adapter.cards) == 1

    await env.processor.on_callback(
        tap_event("tg", "owner", "collection:recipes", sender_id="owner-1")
    )

    assert len(env.ingest.calls) == 1
    assert env.ingest.calls[0]["collection"] == "recipes"
    assert env.ingest.calls[0]["filename"] == "scan.pdf"
    assert any("recipes" in text for _chat, text in adapter.sent)

    # The document was consumed: tapping again has nothing left to act on.
    env.ingest.calls.clear()
    await env.processor.on_callback(
        tap_event("tg", "owner", "collection:research", sender_id="owner-1")
    )
    assert env.ingest.calls == []


async def test_a_conversion_failure_is_reported_in_one_line_and_consumes_the_pending_document(
    env: ChannelEnv, tmp_path: Any
) -> None:
    _resource, adapter = await env.paired_channel(sender_id="owner-1")
    env.collections.names = ["research"]
    env.ingest.fails_with = ValueError("unsupported document type: '.exe'")
    attachment = _attach(tmp_path, name="virus.exe", body=b"MZ")

    await _send_document(env, adapter, attachment, sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "/save research", sender_id="owner-1"))

    assert len(env.ingest.calls) == 1
    [reason] = [text for _chat, text in adapter.sent if "virus.exe" in text]
    assert "unsupported document type" in reason
    assert "Traceback" not in reason

    # Nothing left pending — the same failing bytes are not silently retried.
    env.ingest.fails_with = None
    await env.processor.on_message(inbound("tg", "owner", "/save research", sender_id="owner-1"))
    assert len(env.ingest.calls) == 1  # unchanged: /save had nothing to act on


async def test_help_lists_save(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(inbound("tg", "owner", "/help", sender_id="owner-1"))

    [help_text] = [text for _chat, text in adapter.sent]
    assert "/save" in help_text
