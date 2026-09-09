from coffer.application.async_ops.registry import AsyncOpRegistry, OpState


def test_mark_and_get_transitions():
    reg = AsyncOpRegistry()
    assert reg.get("kb_reembed", "s1") is None

    reg.mark_queued("kb_reembed", "s1")
    assert reg.get("kb_reembed", "s1").state is OpState.queued  # type: ignore[union-attr]

    reg.mark_running("kb_reembed", "s1")
    assert reg.get("kb_reembed", "s1").state is OpState.running  # type: ignore[union-attr]

    reg.clear("kb_reembed", "s1")
    assert reg.get("kb_reembed", "s1") is None


def test_error_records_message():
    reg = AsyncOpRegistry()
    reg.mark_error("kb_reembed", "s1", "boom")
    entry = reg.get("kb_reembed", "s1")
    assert entry is not None
    assert entry.state is OpState.error
    assert entry.message == "boom"


def test_snapshot_filters_by_op_type_and_prefix():
    reg = AsyncOpRegistry()
    reg.mark_queued("kb_reembed", "agentA:s1")
    reg.mark_running("kb_reembed", "agentA:s2")
    reg.mark_queued("kb_reembed", "agentB:s3")
    reg.mark_queued("ingest", "agentA:doc1")

    kb_all = reg.snapshot("kb_reembed")
    assert set(kb_all) == {"agentA:s1", "agentA:s2", "agentB:s3"}

    agent_a = reg.snapshot("kb_reembed", prefix="agentA:")
    assert set(agent_a) == {"agentA:s1", "agentA:s2"}
    assert agent_a["agentA:s2"].state is OpState.running

    assert set(reg.snapshot("ingest")) == {"agentA:doc1"}


def test_clear_is_idempotent():
    reg = AsyncOpRegistry()
    reg.clear("kb_reembed", "missing")  # no raise
    assert reg.snapshot("kb_reembed") == {}
