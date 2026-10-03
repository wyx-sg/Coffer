"""Questions an agent asks the owner mid-turn (spec chat "Pause a turn on a
question for the owner").

Driven through the real turn orchestrator with scripted adapters: an adapter
asks through ``asker_for`` exactly as the Claude Code hook and the
``coffer__ask`` gateway path do, and the owner answers through the one
``answer_question`` function the REST route and the channels share.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat import questions
from coffer.application.chat.question_agents import QuestionService, answers_payload, asker_for
from coffer.application.chat.questions import AnswerInput, QuestionOutcome
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.chat.turn_state import stop_all_turns
from coffer.domain.chat.errors import QuestionAnswerInvalid, QuestionClosed
from coffer.domain.chat.events import (
    AgentEvent,
    QuestionAsked,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnStarted,
)
from coffer.domain.chat.events import (
    QuestionClosed as QuestionClosedEvent,
)
from coffer.domain.chat.message import Role, TextBlock, ToolResultBlock, ToolUseBlock
from coffer.domain.chat.question import QuestionBlock, check_answer, parse_ask_input
from tests.support.chat_turns import start_turn
from tests.unit.chat.conftest import (
    FakeAgentProvider,
    FakeConversationRepo,
    FakeMessageRepo,
    make_registry,
)

pytestmark = pytest.mark.asyncio

_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

YES_NO: dict[str, Any] = {
    "questions": [
        {
            "header": "Apply",
            "question": "Apply this change to staging?",
            "options": [{"label": "Yes"}, {"label": "No", "description": "Keep it local"}],
        }
    ]
}

TWO: dict[str, Any] = {
    "context": "```diff\n- a\n+ b\n```",
    "questions": [
        {
            "header": "Env",
            "question": "Which environment?",
            "options": [{"label": "staging"}, {"label": "live"}],
        },
        {
            "header": "Parts",
            "question": "Which parts?",
            "multiSelect": True,
            "options": [{"label": "api"}, {"label": "web"}, {"label": "docs"}],
        },
    ],
}


@pytest.fixture(autouse=True)
def _clean_questions() -> Any:
    questions.clear_all()
    yield
    questions.clear_all()


class AskingAdapter:
    """Asks one question the way an agent does, then finishes the turn."""

    model_id = None

    def __init__(self, conversation_id: str, ask_input: dict[str, Any], *, as_tool: str) -> None:
        self.conversation_id = conversation_id
        self.ask_input = ask_input
        self.as_tool = as_tool
        self.outcome: QuestionOutcome | None = None

    async def run_turn(self, *, history: Any, **_: object) -> AsyncIterator[AgentEvent]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text="Checking. ")
        ask = asker_for(self.conversation_id)
        assert ask is not None, "the turn registered no token for its adapter"
        yield ToolCall(tool_use_id="t1", tool_name=self.as_tool, tool_input=self.ask_input)
        self.outcome = await ask(self.ask_input)
        yield ToolResult(tool_use_id="t1", tool_name=self.as_tool, output={"x": 1}, error=None)
        yield TextDelta(text="Done.")
        yield _DONE


class _AskingProvider(FakeAgentProvider):
    def __init__(self, ask_input: dict[str, Any], *, as_tool: str = "AskUserQuestion") -> None:
        super().__init__(None)
        self.ask_input = ask_input
        self.as_tool = as_tool
        self.adapters: list[AskingAdapter] = []

    async def build_adapter(self, conversation_id: str) -> Any:
        adapter = AskingAdapter(conversation_id, self.ask_input, as_tool=self.as_tool)
        self.adapters.append(adapter)
        return adapter


def _make(
    ask_input: dict[str, Any] = YES_NO,
    *,
    as_tool: str = "AskUserQuestion",
    idle_timeout: float | None = 300.0,
) -> tuple[TurnOrchestrator, ChatService, _AskingProvider]:
    provider = _AskingProvider(ask_input, as_tool=as_tool)
    registry, _ = make_registry(provider=provider)
    chat = ChatService(
        conversations=FakeConversationRepo(), messages=FakeMessageRepo(), registry=registry
    )
    orchestrator = TurnOrchestrator(
        chat_service=chat, registry=registry, idle_timeout=idle_timeout, flush_interval=None
    )
    return orchestrator, chat, provider


async def _until_pending(conversation_id: str) -> QuestionBlock:
    for _ in range(200):
        block = questions.pending_question_for(conversation_id)
        if block is not None:
            return block
        await asyncio.sleep(0.005)
    raise AssertionError("the turn never raised its question")


async def _drain(queue: asyncio.Queue[AgentEvent | None]) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=5.0)
        if item is None:
            return events
        events.append(item)


# --------------------------------------------------------------------------
# The question model
# --------------------------------------------------------------------------


async def test_an_ask_is_parsed_into_questions_and_options() -> None:
    context, specs = parse_ask_input(TWO)
    assert context == "```diff\n- a\n+ b\n```"
    assert [s.header for s in specs] == ["Env", "Parts"]
    assert [o.label for o in specs[1].options] == ["api", "web", "docs"]
    assert specs[1].multi_select is True and specs[0].multi_select is False
    _, yes_no = parse_ask_input(YES_NO)
    assert yes_no[0].options[1].description == "Keep it local"


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"questions": []},
        {"questions": [{"question": "q", "options": [{"label": "only"}]}]},
        {"questions": [{"question": "q", "options": [{"label": "a"}, {"label": "a"}]}]},
        {"questions": [{"question": " ", "options": [{"label": "a"}, {"label": "b"}]}]},
        {"questions": [{"question": "q", "options": [{"label": str(i)} for i in range(5)]}]},
        {"questions": [{"question": "q", "options": [{"label": "a"}, {"nolabel": 1}]}]},
    ],
)
async def test_a_malformed_ask_is_refused_with_a_reason(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        parse_ask_input(bad)


async def test_an_answer_must_fit_its_question() -> None:
    (single,) = parse_ask_input(YES_NO)[1]
    assert check_answer(single, ["Yes"], None).display() == "Yes"
    # Free text is an answer on its own — the "Other" the owner types.
    assert check_answer(single, [], "  only the replica ").display() == "only the replica"
    for selected, text in ((["Maybe"], None), (["Yes", "No"], None), ([], None), ([], "  ")):
        with pytest.raises(QuestionAnswerInvalid):
            check_answer(single, selected, text)
    multi = parse_ask_input(TWO)[1][1]
    assert check_answer(multi, ["api", "docs"], None).display() == "api, docs"


# --------------------------------------------------------------------------
# A turn waits, and gets the answer
# --------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="chat", scenario="AskUserQuestion waits for the owner and gets the answer"
)
async def test_a_question_pauses_the_turn_and_the_answer_goes_back_to_the_agent() -> None:
    orchestrator, chat, provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "deploy it")

    block = await _until_pending(conv.id)
    assert block.status == "pending" and block.questions[0].question.startswith("Apply this")
    assert questions.needs_you(conv.id) and questions.needs_you_conversations() == {conv.id}
    assert provider.adapters[0].outcome is None  # the turn is waiting, not running on

    answered = await questions.answer_question(
        conv.id, block.question_id, [AnswerInput(selected=["Yes"])], via="web", by="ui"
    )
    assert answered.status == "answered" and answered.answered_via == "web"
    events = await _drain(queue)

    outcome = provider.adapters[0].outcome
    assert outcome is not None and outcome.answered
    assert [a.display() for a in outcome.block.answers] == ["Yes"]
    assert not questions.needs_you(conv.id)
    asked = [e for e in events if isinstance(e, QuestionAsked)]
    closed = [e for e in events if isinstance(e, QuestionClosedEvent)]
    assert len(asked) == 1 and len(closed) == 1
    assert closed[0].question.status == "answered"

    messages = await chat.list_messages(conv.id)
    # No user message was added for the answer, and the dialog tool is no card.
    assert [m.role for m in messages] == [Role.USER, Role.ASSISTANT]
    reply = messages[1]
    persisted = [b for b in reply.content if isinstance(b, QuestionBlock)]
    assert len(persisted) == 1
    assert persisted[0].status == "answered" and persisted[0].answered_via == "web"
    assert persisted[0].answers[0].selected == ("Yes",) and persisted[0].answered_at
    assert not any(isinstance(b, (ToolUseBlock, ToolResultBlock)) for b in reply.content)
    texts = [b.text for b in reply.content if isinstance(b, TextBlock)]
    assert texts == ["Checking. ", "Done."]


async def test_coffer_ask_through_mcp_is_also_not_shown_as_a_tool_card() -> None:
    orchestrator, chat, _provider = _make(as_tool="mcp__coffer__coffer__ask")
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)
    await questions.answer_question(
        conv.id, block.question_id, [AnswerInput(text="only staging")], via="web", by="ui"
    )
    events = await _drain(queue)
    assert not any(isinstance(e, (ToolCall, ToolResult)) for e in events)


@pytest.mark.acceptance(spec="chat", scenario="the second answer to one question is refused")
async def test_the_first_answer_wins_and_a_later_one_is_refused() -> None:
    orchestrator, chat, provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)

    await questions.answer_question(
        conv.id, block.question_id, [AnswerInput(selected=["Yes"])], via="chan-uid", by="owner"
    )
    with pytest.raises(QuestionClosed):
        await questions.answer_question(
            conv.id, block.question_id, [AnswerInput(selected=["No"])], via="web", by="ui"
        )
    await _drain(queue)

    outcome = provider.adapters[0].outcome
    assert outcome is not None and outcome.block.answers[0].selected == ("Yes",)
    (reply,) = [m for m in await chat.list_messages(conv.id) if m.role is Role.ASSISTANT]
    (persisted,) = [b for b in reply.content if isinstance(b, QuestionBlock)]
    assert persisted.answers[0].selected == ("Yes",) and persisted.answered_via == "chan-uid"


async def test_two_answers_at_once_resolve_to_exactly_one() -> None:
    orchestrator, chat, _provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)

    results = await asyncio.gather(
        questions.answer_question(
            conv.id, block.question_id, [AnswerInput(selected=["Yes"])], via="web", by="a"
        ),
        questions.answer_question(
            conv.id, block.question_id, [AnswerInput(selected=["No"])], via="web", by="b"
        ),
        return_exceptions=True,
    )
    await _drain(queue)
    assert sum(isinstance(r, QuestionBlock) for r in results) == 1
    assert sum(isinstance(r, QuestionClosed) for r in results) == 1


async def test_an_answer_for_another_conversation_or_an_unknown_question_is_closed() -> None:
    orchestrator, chat, _provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)
    for conversation_id, question_id in (("other", block.question_id), (conv.id, "nope")):
        with pytest.raises(QuestionClosed):
            await questions.answer_question(
                conversation_id, question_id, [AnswerInput(selected=["Yes"])], via="web", by="ui"
            )
    # Still pending: a refused answer changes nothing.
    assert questions.pending_question_for(conv.id) is not None
    orchestrator.interrupt_turn(conv.id)
    await _drain(queue)


async def test_an_invalid_answer_changes_nothing() -> None:
    orchestrator, chat, _provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)
    with pytest.raises(QuestionAnswerInvalid):
        await questions.answer_question(
            conv.id, block.question_id, [AnswerInput(selected=["Maybe"])], via="web", by="ui"
        )
    pending = questions.pending_question_for(conv.id)
    assert pending is not None and pending.answers == ()
    orchestrator.interrupt_turn(conv.id)
    await _drain(queue)


async def test_several_questions_are_answered_one_at_a_time_in_order() -> None:
    orchestrator, chat, provider = _make(TWO)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)
    progress: list[QuestionBlock] = []
    questions.add_progress_listener(lambda _cid, b: progress.append(b))

    first = await questions.answer_question(
        conv.id, block.question_id, [AnswerInput(selected=["staging"])], via="web", by="ui"
    )
    assert first.status == "pending" and first.next_index == 1
    assert questions.pending_question_for(conv.id) is not None
    # A card answered twice: the index says which question this tap was for.
    with pytest.raises(QuestionClosed):
        await questions.answer_question(
            conv.id,
            block.question_id,
            [AnswerInput(selected=["live"])],
            via="web",
            by="ui",
            index=0,
        )
    # Text typed while it waits answers the first unanswered question.
    last = await questions.answer_pending_with_text(conv.id, "api and web", via="web", by="ui")
    assert last is not None and last.status == "answered"
    events = await _drain(queue)

    assert [a.display() for a in last.answers] == ["staging", "api and web"]
    assert len(progress) == 1 and progress[0].next_index == 1
    asked = [e for e in events if isinstance(e, QuestionAsked)]
    assert len(asked) == 2, "the first answer re-sends the block, still pending"
    outcome = provider.adapters[0].outcome
    assert outcome is not None
    assert answers_payload(outcome.block)[1] == {
        "header": "Parts",
        "question": "Which parts?",
        "selected": [],
        "text": "api and web",
    }


async def test_a_multi_select_answer_carries_every_label() -> None:
    orchestrator, chat, provider = _make(TWO)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)
    await questions.answer_question(
        conv.id,
        block.question_id,
        [AnswerInput(selected=["live"]), AnswerInput(selected=["api", "docs"])],
        via="web",
        by="ui",
    )
    await _drain(queue)
    outcome = provider.adapters[0].outcome
    assert outcome is not None
    assert answers_payload(outcome.block)[1]["selected"] == ["api", "docs"]


async def test_text_with_nothing_pending_is_not_an_answer() -> None:
    assert await questions.answer_pending_with_text("c", "hello", via="web", by="ui") is None


# --------------------------------------------------------------------------
# Listeners
# --------------------------------------------------------------------------


async def test_listeners_hear_a_question_raised_and_closed() -> None:
    orchestrator, chat, _provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    raised: list[tuple[str, QuestionBlock]] = []
    closed: list[tuple[str, QuestionBlock]] = []
    questions.add_raised_listener(lambda cid, b: raised.append((cid, b)))
    remove = questions.add_closed_listener(lambda cid, b: closed.append((cid, b)))
    questions.add_raised_listener(lambda *_: 1 / 0)  # a failing listener is skipped

    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)
    assert raised == [(conv.id, block)]
    await questions.answer_question(
        conv.id, block.question_id, [AnswerInput(selected=["No"])], via="chan", by="owner"
    )
    await _drain(queue)
    assert [(c, b.status) for c, b in closed] == [(conv.id, "answered")]
    remove()


# --------------------------------------------------------------------------
# Cancelling
# --------------------------------------------------------------------------


@pytest.mark.acceptance(spec="chat", scenario="stopping a turn cancels its question")
async def test_stopping_the_turn_cancels_the_question_and_tells_the_agent() -> None:
    orchestrator, chat, provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    await _until_pending(conv.id)
    closed: list[QuestionBlock] = []
    questions.add_closed_listener(lambda _cid, b: closed.append(b))

    orchestrator.interrupt_turn(conv.id)
    events = await _drain(queue)

    assert not questions.needs_you(conv.id) and questions.token_for(conv.id) is None
    assert [b.status for b in closed] == ["cancelled"]
    assert any(isinstance(e, QuestionClosedEvent) for e in events)
    assert any(isinstance(e, TurnDone) and e.stop_reason == "interrupted" for e in events)
    reply = next(m for m in await chat.list_messages(conv.id) if m.role is Role.ASSISTANT)
    assert reply.status == "stopped"
    (persisted,) = [b for b in reply.content if isinstance(b, QuestionBlock)]
    assert persisted.status == "cancelled"
    # The adapter was cancelled with its turn; the waiting call is released.
    assert provider.adapters[0].outcome is None


async def test_a_turn_that_ends_cancels_a_question_still_pending() -> None:
    ctx = questions.register_turn("c1")
    seen: list[AgentEvent] = []

    async def sink(event: AgentEvent) -> None:
        seen.append(event)

    ctx.on_event = sink
    waiter = asyncio.create_task(questions.raise_question(ctx.token, YES_NO))
    for _ in range(50):
        await asyncio.sleep(0)
    assert questions.needs_you("c1")

    await questions.close_turn(ctx)
    outcome = await waiter

    assert not outcome.answered and outcome.message == questions.MSG_STOPPED
    assert [type(e) for e in seen] == [QuestionAsked, QuestionClosedEvent]
    assert not questions.needs_you("c1")


async def test_a_daemon_shutdown_cancels_the_pending_question() -> None:
    orchestrator, chat, _provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    await _until_pending(conv.id)

    await stop_all_turns()
    await _drain(queue)

    assert not questions.needs_you(conv.id)
    reply = next(m for m in await chat.list_messages(conv.id) if m.role is Role.ASSISTANT)
    assert reply.status == "failed"
    assert [b.status for b in reply.content if isinstance(b, QuestionBlock)] == ["cancelled"]


async def test_deleting_the_conversation_cancels_its_question() -> None:
    orchestrator, chat, _provider = _make()
    conv = await chat.create_conversation(agent_key="builtin")
    await start_turn(orchestrator, conv.id, "go")
    await _until_pending(conv.id)

    await chat.delete_conversation(conv.id, cancel_turn_fn=orchestrator.cancel_turn)
    for _ in range(50):
        await asyncio.sleep(0)
    assert not questions.needs_you(conv.id)


async def test_a_question_nobody_answers_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(questions, "EXPIRY_SECONDS", 0.05)
    ctx = questions.register_turn("c2")
    outcome = await questions.raise_question(ctx.token, YES_NO)
    assert not outcome.answered and outcome.block.status == "cancelled"
    assert outcome.message == questions.MSG_EXPIRED
    assert not questions.needs_you("c2")
    questions.release_turn(ctx)


async def test_an_abandoned_ask_closes_its_question() -> None:
    """The agent's call is cancelled (its process died): nobody waits any more."""
    ctx = questions.register_turn("c3")
    waiter = asyncio.create_task(questions.raise_question(ctx.token, YES_NO))
    for _ in range(50):
        await asyncio.sleep(0)
    assert questions.needs_you("c3")
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not questions.needs_you("c3")
    questions.release_turn(ctx)


async def test_an_ask_without_a_live_turn_is_refused() -> None:
    with pytest.raises(ValueError, match="not running"):
        await questions.raise_question("no-such-token", YES_NO)
    ctx = questions.register_turn("c4")
    with pytest.raises(ValueError, match="questions"):
        await questions.raise_question(ctx.token, {"questions": []})
    questions.release_turn(ctx)


# --------------------------------------------------------------------------
# The turn's token, and the idle watchdog
# --------------------------------------------------------------------------


async def test_a_turn_token_lives_exactly_as_long_as_the_turn() -> None:
    tokens: list[str | None] = []

    class _Peek(AskingAdapter):
        async def _gen(self) -> AsyncIterator[AgentEvent]:
            tokens.append(questions.token_for(self.conversation_id))
            yield TurnStarted()
            yield _DONE

    provider = _AskingProvider(YES_NO)

    async def build(conversation_id: str) -> Any:
        return _Peek(conversation_id, YES_NO, as_tool="x")

    provider.build_adapter = build  # type: ignore[method-assign]
    registry, _ = make_registry(provider=provider)
    chat = ChatService(
        conversations=FakeConversationRepo(), messages=FakeMessageRepo(), registry=registry
    )
    orchestrator = TurnOrchestrator(chat_service=chat, registry=registry, flush_interval=None)
    conv = await chat.create_conversation(agent_key="builtin")
    assert questions.turn_env(conv.id) == {}

    queue = await start_turn(orchestrator, conv.id, "go")
    await _drain(queue)

    (token,) = tokens
    assert token and len(token) >= 32
    service = QuestionService()
    assert not service.is_live(token) and not service.is_live(None)
    assert questions.turn_env(conv.id) == {}


async def test_a_waiting_turn_is_not_cut_off_by_the_idle_watchdog() -> None:
    """Five minutes of silence ends a wedged turn; a turn waiting on the owner
    is silent on purpose."""
    orchestrator, chat, provider = _make(idle_timeout=0.1)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)

    await asyncio.sleep(0.35)  # three watchdog periods
    assert questions.needs_you(conv.id), "the watchdog ended a turn waiting on the owner"

    await questions.answer_question(
        conv.id, block.question_id, [AnswerInput(selected=["Yes"])], via="web", by="ui"
    )
    events = await _drain(queue)
    assert any(isinstance(e, TurnDone) and e.stop_reason == "end_turn" for e in events)
    assert provider.adapters[0].outcome is not None


async def test_the_watchdog_resumes_once_the_question_is_answered() -> None:
    class _Stall(AskingAdapter):
        async def _gen(self) -> AsyncIterator[AgentEvent]:
            yield TurnStarted()
            ask = asker_for(self.conversation_id)
            assert ask is not None
            self.outcome = await ask(self.ask_input)
            await asyncio.sleep(3600)  # wedged after the answer
            yield _DONE

    provider = _AskingProvider(YES_NO)

    async def build(conversation_id: str) -> Any:
        return _Stall(conversation_id, YES_NO, as_tool="x")

    provider.build_adapter = build  # type: ignore[method-assign]
    registry, _ = make_registry(provider=provider)
    chat = ChatService(
        conversations=FakeConversationRepo(), messages=FakeMessageRepo(), registry=registry
    )
    orchestrator = TurnOrchestrator(
        chat_service=chat, registry=registry, idle_timeout=0.1, flush_interval=None
    )
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _until_pending(conv.id)
    await asyncio.sleep(0.25)
    await questions.answer_question(
        conv.id, block.question_id, [AnswerInput(selected=["Yes"])], via="web", by="ui"
    )
    events = await _drain(queue)
    assert any(getattr(e, "code", None) == "turn_timeout" for e in events)
