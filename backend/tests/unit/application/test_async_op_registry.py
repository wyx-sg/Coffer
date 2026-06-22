from coffer.application.async_ops.registry import AsyncOpRegistry, OpState


def test_mark_and_get_transitions():
    reg = AsyncOpRegistry()
    assert reg.get("distill", "s1") is None

    reg.mark_queued("distill", "s1")
    assert reg.get("distill", "s1").state is OpState.queued  # type: ignore[union-attr]

    reg.mark_running("distill", "s1")
    assert reg.get("distill", "s1").state is OpState.running  # type: ignore[union-attr]

    reg.clear("distill", "s1")
    assert reg.get("distill", "s1") is None


def test_error_records_message():
    reg = AsyncOpRegistry()
    reg.mark_error("distill", "s1", "boom")
    entry = reg.get("distill", "s1")
    assert entry is not None
    assert entry.state is OpState.error
    assert entry.message == "boom"


def test_snapshot_filters_by_op_type_and_prefix():
    reg = AsyncOpRegistry()
    reg.mark_queued("distill", "agentA:s1")
    reg.mark_running("distill", "agentA:s2")
    reg.mark_queued("distill", "agentB:s3")
    reg.mark_queued("ingest", "agentA:doc1")

    distill_all = reg.snapshot("distill")
    assert set(distill_all) == {"agentA:s1", "agentA:s2", "agentB:s3"}

    agent_a = reg.snapshot("distill", prefix="agentA:")
    assert set(agent_a) == {"agentA:s1", "agentA:s2"}
    assert agent_a["agentA:s2"].state is OpState.running

    assert set(reg.snapshot("ingest")) == {"agentA:doc1"}


def test_clear_is_idempotent():
    reg = AsyncOpRegistry()
    reg.clear("distill", "missing")  # no raise
    assert reg.snapshot("distill") == {}
