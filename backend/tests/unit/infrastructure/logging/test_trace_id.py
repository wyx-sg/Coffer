from coffer.infrastructure.logging.setup import bind_trace_id, get_trace_id


def test_bind_and_get_trace_id():
    bind_trace_id("abc-123")
    assert get_trace_id() == "abc-123"


def test_trace_id_defaults_to_dash():
    bind_trace_id(None)
    assert get_trace_id() == "-"
