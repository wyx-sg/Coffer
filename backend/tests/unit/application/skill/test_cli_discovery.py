"""Walking a tool's help tree: what it asks the runner for, and where it
stops (spec skill-manager "Serve required commands on REST and the web")."""

from __future__ import annotations

from coffer.application.skill.cli_discovery import discover
from coffer.domain.skill.cli_help import DiscoveryStatus
from tests.support.cli_requirements import DEMO_HELP, FakeHelpRunner


def _group(*names: str) -> str:
    return "Usage: x [OPTIONS] COMMAND\n\nCommands:\n" + "".join(
        f"  {n}  Does {n}\n" for n in names
    )


def test_walks_every_listed_subcommand_once() -> None:
    runner = FakeHelpRunner(dict(DEMO_HELP))
    found = discover(runner, "/bin/demo")
    assert found.status is DiscoveryStatus.OK and not found.incomplete
    assert [n.path for n in found.nodes] == [(), ("init",), ("run",)]
    assert found.nodes[1].options[0].names == ("--force",)
    assert found.nodes[2].arguments[0].name == "TARGET"
    assert runner.calls == [
        ("/bin/demo", (), "--help"),
        ("/bin/demo", ("init",), "--help"),
        ("/bin/demo", ("run",), "--help"),
    ]


def test_only_help_flags_are_ever_asked_for() -> None:
    runner = FakeHelpRunner({(): _group("a"), ("a",): ""})
    discover(runner, "/bin/x")
    assert {flag for _p, _s, flag in runner.calls} <= {"--help", "-h", "help"}
    # a node with no output falls back to -h, and the root also to help
    assert ("/bin/x", ("a",), "-h") in runner.calls
    assert ("/bin/x", ("a",), "help") not in runner.calls


def test_no_help_at_the_root_is_reported() -> None:
    runner = FakeHelpRunner()
    found = discover(runner, "/bin/x")
    assert ("/bin/x", (), "help") in runner.calls
    assert found.status is DiscoveryStatus.NO_HELP and found.nodes == ()
    assert "printed nothing" in (found.message or "")


def test_depth_is_bounded() -> None:
    texts = {(): _group("a"), ("a",): _group("b"), ("a", "b"): _group("c")}
    texts[("a", "b", "c")] = _group("d")
    texts[("a", "b", "c", "d")] = _group("e")
    found = discover(FakeHelpRunner(texts), "/bin/x", max_depth=3)
    assert max(len(n.path) for n in found.nodes) == 3
    assert found.incomplete


def test_node_count_is_bounded() -> None:
    texts = {(): _group(*[f"c{i}" for i in range(30)])}
    texts.update({(f"c{i}",): _group("leaf") for i in range(30)})
    found = discover(FakeHelpRunner(texts), "/bin/x", max_nodes=10)
    assert len(found.nodes) == 10 and found.incomplete


def test_time_budget_is_bounded() -> None:
    clock = iter(range(1000))
    texts = {(): _group("a", "b", "c")}
    texts.update({(n,): "Usage: x\n" for n in "abc"})
    found = discover(
        FakeHelpRunner(texts), "/bin/x", budget=1.5, monotonic=lambda: float(next(clock))
    )
    assert found.incomplete and len(found.nodes) < 4


def test_a_subcommand_that_prints_its_parents_help_is_not_a_node() -> None:
    parent = _group("a")
    found = discover(FakeHelpRunner({(): parent, ("a",): parent}), "/bin/x")
    assert [n.path for n in found.nodes] == [()]


def test_help_is_not_walked_into() -> None:
    runner = FakeHelpRunner({(): _group("help", "go"), ("go",): "Usage: x go\n"})
    discover(runner, "/bin/x")
    assert all("help" not in sub for _p, sub, _f in runner.calls)


def test_a_subcommand_with_no_help_is_a_node_with_an_error() -> None:
    found = discover(FakeHelpRunner({(): _group("a")}), "/bin/x")
    assert found.nodes[1].path == ("a",) and found.nodes[1].error == "printed no help"
