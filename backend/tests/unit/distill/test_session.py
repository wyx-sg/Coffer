from coffer.domain.distill.session import (
    DistilledInsight,
    TranscriptMessage,
    TranscriptSession,
)


def test_insight_holds_name_description_body():
    insight = DistilledInsight(
        name="Use ULIDs for ids",
        description="Project standard",
        body="IDs are ULIDs, not UUIDs.",
    )
    assert insight.name == "Use ULIDs for ids"
    assert insight.description == "Project standard"
    assert insight.body == "IDs are ULIDs, not UUIDs."


def test_session_counts_messages_and_keeps_project_path():
    msgs = (
        TranscriptMessage(role="user", text="hi"),
        TranscriptMessage(role="assistant", text="hello"),
    )
    s = TranscriptSession(
        session_id="abc",
        agent_type_value="claude_code",
        project_path="/repo",
        started_at=None,
        messages=msgs,
        source_path="/x.jsonl",
    )
    assert s.message_count == 2
    assert s.project_path == "/repo"
