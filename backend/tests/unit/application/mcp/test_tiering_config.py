from coffer.application.mcp.tiering_config import load_tiering_config


def test_defaults_when_env_is_empty():
    cfg = load_tiering_config({})
    assert cfg.enabled is True
    assert cfg.budget == 50
    assert cfg.window_days == 90


def test_mode_off_disables_tiering():
    assert load_tiering_config({"COFFER_TOOL_TIERING": "off"}).enabled is False
    assert load_tiering_config({"COFFER_TOOL_TIERING": "OFF"}).enabled is False
    assert load_tiering_config({"COFFER_TOOL_TIERING": " off "}).enabled is False


def test_overrides_are_read():
    cfg = load_tiering_config(
        {"COFFER_TOOL_TIERING_BUDGET": "12", "COFFER_TOOL_TIERING_WINDOW_DAYS": "7"}
    )
    assert cfg.budget == 12
    assert cfg.window_days == 7


def test_unparseable_or_nonpositive_values_fall_back_to_defaults():
    """A malformed knob must never shrink the listed catalogue to nothing."""
    for raw in ("abc", "0", "-5", ""):
        assert load_tiering_config({"COFFER_TOOL_TIERING_BUDGET": raw}).budget == 50
        assert load_tiering_config({"COFFER_TOOL_TIERING_WINDOW_DAYS": raw}).window_days == 90


def test_unknown_mode_keeps_tiering_on():
    """Only the explicit 'off' disables it: a typo must not silently restore
    the pre-ADR-046 full-catalogue listing."""
    assert load_tiering_config({"COFFER_TOOL_TIERING": "auto"}).enabled is True
    assert load_tiering_config({"COFFER_TOOL_TIERING": "banana"}).enabled is True


def test_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("COFFER_TOOL_TIERING_BUDGET", "3")
    assert load_tiering_config().budget == 3
