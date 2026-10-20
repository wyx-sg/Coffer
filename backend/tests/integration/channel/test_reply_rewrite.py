"""A reply too long for a chat is said again short (spec channels "Ask for the
short version of a reply too long for a chat"): the long one is never sent, the
same conversation is asked for the short version, and that reply carries a
full-report button whose tap asks the agent for the file."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from coffer.application.channel.reply_rewrite import (
    FULL_REPORT_REQUEST,
    MAX_REPLY_LINES,
    too_long,
)
from coffer.domain.chat.events import (
    AgentEvent,
    MessageEnd,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnStarted,
)

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, tap_event, wait_until

_LONG = "\n".join(f"- finding {i}: something the reader did not need" for i in range(40))
_SHORT = "The sheet is ready. Want the full report as a file?"
_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


class _Agent:
    """Answers long at first, short when Coffer asks, and with a file note when
    the owner asks for the full report."""

    def __init__(self, *, first: str = _LONG, short: str = _SHORT) -> None:
        self.first = first
        self.short = short
        self.prompts: list[str] = []

    async def run_turn(self, prompt: str, attachments: Sequence[Any] = ()) -> Any:
        self.prompts.append(prompt)
        return self._events(prompt)

    async def _events(self, prompt: str) -> AsyncIterator[AgentEvent]:
        if prompt.startswith("[Coffer]"):
            text = self.short
        elif FULL_REPORT_REQUEST in prompt:
            text = "Here is the full report."
        else:
            text = self.first
        for event in (TurnStarted(), TextDelta(text=text), _DONE):
            yield event


async def _setup(env: ChannelEnv, agent: _Agent, **caps: Any) -> FakeChannelAdapter:
    adapter = FakeChannelAdapter(supports_edit=False, **caps)
    env.provider.adapter = agent
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner")
    return adapter


@pytest.mark.acceptance(spec="channels", scenario="a reply too long for a chat is said again short")
async def test_a_long_reply_is_not_sent_and_the_short_one_carries_the_button(
    env: ChannelEnv,
) -> None:
    agent = _Agent()
    adapter = await _setup(env, agent, supports_buttons=True)

    await env.send(inbound("tg", "owner", "build the IA"))
    await wait_until(lambda: _SHORT in adapter.texts())

    assert not any("finding 39" in text for text in adapter.texts())
    assert agent.prompts[1].startswith("[Coffer] Your last reply (40 lines)")
    index = adapter.texts().index(_SHORT)
    assert [b.label for b in adapter.sent_buttons[index]] == ["📄 Full report"]
    # Coffer's note never names the conversation.
    (conversation,) = await env.conversations()
    assert not conversation.title.startswith("[Coffer]")


@pytest.mark.acceptance(
    spec="channels", scenario="the full-report button asks the agent for the file"
)
async def test_the_full_report_tap_is_the_owner_asking_for_the_file(env: ChannelEnv) -> None:
    agent = _Agent()
    adapter = await _setup(env, agent, supports_buttons=True)
    await env.send(inbound("tg", "owner", "build the IA"))
    await wait_until(lambda: _SHORT in adapter.texts())
    button = adapter.sent_buttons[adapter.texts().index(_SHORT)][0]

    await env.processor.on_callback(tap_event("tg", "owner", button.value))
    await env.processor._burst.settled()
    await wait_until(lambda: "Here is the full report." in adapter.texts())

    assert FULL_REPORT_REQUEST in agent.prompts[-1]


async def test_a_tap_from_someone_else_asks_for_nothing(env: ChannelEnv) -> None:
    agent = _Agent()
    adapter = await _setup(env, agent, supports_buttons=True)
    await env.send(inbound("tg", "owner", "build the IA"))
    await wait_until(lambda: _SHORT in adapter.texts())
    asked = len(agent.prompts)

    await env.processor.on_callback(tap_event("tg", "owner", "full:report", sender_id="intruder"))
    await env.processor._burst.settled()

    assert len(agent.prompts) == asked


@pytest.mark.acceptance(spec="channels", scenario="the short version is never shortened again")
async def test_a_short_version_that_is_still_long_goes_out_as_it_is(env: ChannelEnv) -> None:
    agent = _Agent(short=_LONG)
    adapter = await _setup(env, agent)

    await env.send(inbound("tg", "owner", "build the IA"))
    await wait_until(lambda: any("finding 39" in text for text in adapter.texts()))

    assert len(agent.prompts) == 2


async def test_a_reply_that_fits_goes_out_without_a_follow_up(env: ChannelEnv) -> None:
    agent = _Agent(first="Done: the IA is created.")
    adapter = await _setup(env, agent, supports_buttons=True)

    await env.send(inbound("tg", "owner", "build the IA"))
    await wait_until(lambda: "Done: the IA is created." in adapter.texts())

    assert len(agent.prompts) == 1
    assert adapter.sent_buttons[adapter.texts().index("Done: the IA is created.")] == []


def test_the_bound_counts_lines_and_characters_but_not_files_or_collapsed_details() -> None:
    lines = "\n".join(f"line {i}" for i in range(MAX_REPLY_LINES))
    assert not too_long(lines)
    assert too_long(lines + "\none more")
    assert too_long("字" * 1501)
    assert not too_long(lines + "\nMEDIA:/tmp/report.md")
    details = "Deploy is green.\n## Details\n" + "\n".join("x" for _ in range(50))
    assert too_long(details)
    assert not too_long(details, collapses_details=True)


@pytest.mark.acceptance(
    spec="channels", scenario="narration the agent marked never reaches the reply"
)
async def test_narration_the_agent_marked_never_reaches_the_reply(env: ChannelEnv) -> None:
    class _Narrating:
        async def run_turn(self, prompt: str, attachments: Sequence[Any] = ()) -> Any:
            return self._events()

        async def _events(self) -> AsyncIterator[AgentEvent]:
            for event in (
                TurnStarted(),
                TextDelta(text="I must not claim the format is done."),
                MessageEnd(commentary=True),
                ToolCall(tool_use_id="t1", tool_name="mcp__sheets__read", tool_input={}),
                ToolResult(tool_use_id="t1", tool_name="mcp__sheets__read", output={}, error=None),
                TextDelta(text="Checking the header row next."),
                MessageEnd(commentary=True),
                TextDelta(text="The IA tab is ready."),
                MessageEnd(commentary=False),
                _DONE,
            ):
                yield event

    adapter = FakeChannelAdapter(supports_edit=False)
    env.provider.adapter = _Narrating()
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner")

    await env.send(inbound("tg", "owner", "build the IA"))
    await wait_until(lambda: "The IA tab is ready." in adapter.texts())

    assert adapter.texts()[-1] == "The IA tab is ready."
