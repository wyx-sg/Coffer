from coffer.domain.mcp.tool_tiering import (
    DEFAULT_BUDGET,
    select_listed_tools,
    split_prefixed,
)

PREFIX = "coffer__"


def _tool(name: str) -> dict:
    return {"name": name, "description": f"does {name}", "inputSchema": {}}


def _catalogue(server: str, n: int) -> list[dict]:
    return [_tool(f"{server}__t{i}") for i in range(n)]


def _names(result) -> list[str]:
    return [t["name"] for t in result.listed]


def test_under_budget_lists_everything():
    tools = [_tool("coffer__recall"), *_catalogue("jira", 10)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=DEFAULT_BUDGET)

    assert _names(result) == [t["name"] for t in tools]
    assert result.hidden_count == 0


def test_exactly_at_budget_lists_everything():
    tools = _catalogue("jira", 10)

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=10)

    assert len(result.listed) == 10
    assert result.hidden_count == 0


def test_builtins_are_always_listed_even_over_budget():
    tools = [_tool("coffer__search_tools"), _tool("coffer__recall"), *_catalogue("jira", 80)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=10)

    assert "coffer__search_tools" in _names(result)
    assert "coffer__recall" in _names(result)
    assert len(result.listed) == 12  # 2 builtins + 10 upstream
    assert result.hidden_count == 70


def test_builtins_do_not_consume_the_upstream_budget():
    tools = [_tool("coffer__recall"), *_catalogue("jira", 20)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=5)

    upstream = [n for n in _names(result) if not n.startswith(PREFIX)]
    assert len(upstream) == 5


def test_used_tools_outrank_unused_ones():
    tools = _catalogue("jira", 30)
    usage = {("jira", "t29"): 10, ("jira", "t28"): 5}

    result = select_listed_tools(tools, usage, builtin_prefix=PREFIX, budget=3)

    listed = _names(result)
    assert "jira__t29" in listed
    assert "jira__t28" in listed


def test_every_server_keeps_at_least_one_tool():
    """A server whose tools are all unused must still reach the agent."""
    tools = [*_catalogue("jira", 40), *_catalogue("seatalk", 5)]
    usage = {("jira", f"t{i}"): 100 - i for i in range(40)}

    result = select_listed_tools(tools, usage, builtin_prefix=PREFIX, budget=10)

    listed = _names(result)
    assert any(n.startswith("seatalk__") for n in listed)


def test_server_floor_is_honoured_when_servers_outnumber_the_budget():
    """More servers than budget: the budget wins, but the slice stays sane."""
    tools = [t for s in range(20) for t in _catalogue(f"srv{s}", 3)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=5)

    listed = _names(result)
    assert len(listed) == 5
    # Five distinct servers, not five tools from one server.
    assert len({split_prefixed(n)[0] for n in listed}) == 5


def test_selection_is_deterministic():
    tools = _catalogue("jira", 30)

    first = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=5)
    second = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=5)

    assert _names(first) == _names(second)


def test_listed_tools_keep_catalogue_order():
    tools = _catalogue("jira", 30)
    usage = {("jira", "t20"): 5}

    result = select_listed_tools(tools, usage, builtin_prefix=PREFIX, budget=3)
    order = [t["name"] for t in tools]

    assert _names(result) == sorted(_names(result), key=order.index)


def test_zero_usage_falls_back_to_catalogue_order():
    tools = _catalogue("jira", 30)

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=3)

    assert _names(result) == ["jira__t0", "jira__t1", "jira__t2"]


def test_hidden_count_counts_only_upstream_tools():
    tools = [_tool("coffer__recall"), *_catalogue("jira", 60)]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=50)

    assert result.hidden_count == 10


def test_only_builtins_is_not_an_error():
    tools = [_tool("coffer__recall"), _tool("coffer__search_tools")]

    result = select_listed_tools(tools, {}, builtin_prefix=PREFIX, budget=0)

    assert len(result.listed) == 2
    assert result.hidden_count == 0


def test_split_prefixed_splits_on_the_first_separator():
    assert split_prefixed("jira__jira_get_issue") == ("jira", "jira_get_issue")
    assert split_prefixed("srv__weird__tool") == ("srv", "weird__tool")
    assert split_prefixed("bare") == ("", "bare")


# --- the person's per-tool exposure overrides ---------------------------------


def test_a_pinned_tool_is_listed_even_when_unused_and_over_budget():
    tools = _catalogue("jira", 10)

    result = select_listed_tools(
        tools,
        {("jira", "t0"): 9, ("jira", "t1"): 8},
        builtin_prefix=PREFIX,
        budget=2,
        exposure={"jira__t9": "listed"},
    )

    # The pin takes one of the two slots; the busiest auto tool takes the other.
    assert _names(result) == ["jira__t0", "jira__t9"]
    assert result.hidden_count == 8


def test_a_search_only_tool_is_hidden_even_when_busiest_and_under_budget():
    tools = _catalogue("jira", 3)

    result = select_listed_tools(
        tools,
        {("jira", "t0"): 99},
        builtin_prefix=PREFIX,
        budget=50,
        exposure={"jira__t0": "search"},
    )

    assert _names(result) == ["jira__t1", "jira__t2"]
    assert result.hidden_count == 1


def test_pins_beyond_the_budget_are_all_listed_and_leave_auto_nothing():
    tools = _catalogue("jira", 6)

    result = select_listed_tools(
        tools,
        {("jira", "t5"): 50},
        builtin_prefix=PREFIX,
        budget=2,
        exposure={"jira__t0": "listed", "jira__t1": "listed", "jira__t2": "listed"},
    )

    assert _names(result) == ["jira__t0", "jira__t1", "jira__t2"]


def test_auto_is_the_default_and_matches_no_overrides():
    tools = _catalogue("jira", 8)
    usage = {("jira", "t6"): 3}

    plain = select_listed_tools(tools, usage, builtin_prefix=PREFIX, budget=3)
    empty = select_listed_tools(tools, usage, builtin_prefix=PREFIX, budget=3, exposure={})

    assert _names(plain) == _names(empty)
    assert "jira__t6" in _names(plain)


def test_a_server_whose_tools_are_all_search_only_gets_no_reserved_slot():
    tools = [*_catalogue("quiet", 2), *_catalogue("busy", 3)]

    result = select_listed_tools(
        tools,
        {},
        builtin_prefix=PREFIX,
        budget=2,
        exposure={"quiet__t0": "search", "quiet__t1": "search"},
    )

    assert _names(result) == ["busy__t0", "busy__t1"]
