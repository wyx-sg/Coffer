"""Every ``coffer__`` tool the ``coffer-guide`` skill names must exist.

The skill body is not documentation in the usual sense. Nobody reads it and
decides whether to believe it: it is delivered into an agent's skills
directory, and the thing that opens it is a model that will call whatever it
is told about, by exactly the name it was told. A tool named there that the
gateway does not answer is therefore not a stale sentence — it is an agent
spending a turn on a call that comes back unknown, and then reasoning about
why a capability it was promised is missing.

This repo has shipped that defect class more than once. The handshake
instructions kept naming ``recall`` / ``remember`` / ``search_knowledge`` /
``ask`` after the knowledge layer replaced them, which is why
``test_initialize_instructions`` grew its own version of this gate. The skill
is the larger surface of the two — the instructions are a paragraph, the skill
is the whole manual — and it had no gate at all.

Both halves are checked, because they can fail apart:

* the rendered ``SKILL.md``, which is what an agent actually receives, and
* the static asset on its own, so the gate still holds if the renderer stops
  passing the asset through verbatim.

The registry is assembled here exactly as ``test_initialize_instructions``
assembles it, deliberately by hand rather than through the composition root:
the root needs a database, a daemon and real services, and a gate that cannot
run without them is a gate that gets skipped. The cost is that a registrar
added to the root must be added here too — which is precisely the omission
that let ``coffer__recall`` go unadvertised, so the assembly is spelled out
below rather than hidden behind a helper.
"""

from __future__ import annotations

import pathlib
import re

from coffer.application.knowledge import guide_render
from coffer.domain.knowledge.entry import CollectionEntry, FileEntry

#: Any ``coffer__`` token in running prose. The trailing ``[a-z_]+`` is what
#: keeps the bare prefix — the asset writes "all prefixed ``coffer__``" — from
#: being read as a tool name.
_TOOL_TOKEN = re.compile(r"coffer__[a-z_]+")


def _registered_tool_names() -> set[str]:
    """The bare names the gateway will actually answer."""
    from coffer.application.builtin_tools import BuiltinToolRegistry
    from coffer.application.diagnostics import register_diagnostics_builtin_tools
    from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
    from coffer.application.memory.builtin_recall_tool import register_recall_tool

    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=None,  # type: ignore[arg-type]
    )
    register_diagnostics_builtin_tools(
        registry,
        audit_repo=None,  # type: ignore[arg-type]
        log_path=lambda: pathlib.Path("daemon.log"),
    )
    register_recall_tool(
        registry,
        recall_service=None,  # type: ignore[arg-type]
    )
    # ``search_tools`` is answered by the gateway itself rather than out of the
    # registry, so it is the one name legitimately absent from it.
    return {tool.name for tool in registry.list()} | {"search_tools"}


def _catalogue() -> guide_render.Catalogue:
    """A catalogue with both shapes the renderer branches on.

    One collection with documents and one with none, so the rendered text
    covers the "nothing curated here yet" branch as well — a branch that could
    perfectly well grow a tool name of its own.
    """
    return [
        (
            CollectionEntry(
                name="coffer",
                description="The Coffer project's own knowledge. Notes an agent wrote.",
                source_count=4,
                topic_count=2,
            ),
            [
                FileEntry(
                    path="coffer/topics/gateway.md",
                    title="The MCP gateway",
                    description="How aggregation and tiering fit together.",
                    actor="agent",
                    updated_at="2026-09-18T00:00:00Z",
                ),
                FileEntry(
                    path="coffer/topics/vault/sync.md",
                    title="Vault sync",
                    description="",
                    actor="user",
                    updated_at="2026-09-18T00:00:00Z",
                ),
            ],
        ),
        (
            CollectionEntry(
                name="scratch",
                description="",
                source_count=1,
                topic_count=0,
            ),
            [],
        ),
    ]


def _assert_names_exist(text: str, *, where: str) -> None:
    named = set(_TOOL_TOKEN.findall(text))
    registered = {f"coffer__{name}" for name in _registered_tool_names()}
    for token in sorted(named - registered):
        raise AssertionError(
            f"{where} names {token}, which no registered tool answers. "
            f"named there: {sorted(named)}; registered: {sorted(registered)}"
        )


def test_rendered_skill_names_only_tools_that_exist() -> None:
    """What an agent receives must not promise a tool the gateway lacks."""
    rendered = guide_render.render("~/.coffer/knowledge", _catalogue())
    _assert_names_exist(rendered, where="the rendered coffer-guide skill")


def test_static_asset_names_only_tools_that_exist() -> None:
    """Checked apart from the renderer, so the gate survives it changing.

    ``render`` happens to pass the asset through verbatim today. If it ever
    stops — templating a section out, say — a stale name in the asset would
    slip past a test that only ever reads the rendered output.
    """
    asset = (
        pathlib.Path(guide_render.__file__).parent / "skill_assets" / "coffer-guide.md"
    ).read_text(encoding="utf-8")
    _assert_names_exist(asset, where="the coffer-guide static asset")


def test_rendered_skill_names_every_tool_that_exists() -> None:
    """And the other direction: a tool nobody is told about may as well not exist.

    Coffer has exactly four built-ins and the skill is the one manual every
    agent gets, so "some subset" is not good enough — a tool added to the
    registry and left out of the manual is invisible in practice, which is the
    state ``coffer__recall`` was in.
    """
    rendered = guide_render.render("~/.coffer/knowledge", _catalogue())
    named = set(_TOOL_TOKEN.findall(rendered))
    registered = {f"coffer__{name}" for name in _registered_tool_names()}

    missing = sorted(registered - named)
    assert not missing, (
        f"registered tools the coffer-guide skill never names: {missing}. "
        f"named there: {sorted(named)}; registered: {sorted(registered)}"
    )


def test_handshake_and_skill_agree_on_the_tool_set() -> None:
    """The two always-delivered texts must not describe different Coffers."""
    from coffer.application.mcp.gateway_instructions import NAMED_TOOLS

    rendered = guide_render.render("~/.coffer/knowledge", _catalogue())
    named = {token.removeprefix("coffer__") for token in _TOOL_TOKEN.findall(rendered)}

    assert named == set(NAMED_TOOLS), (
        f"the skill names {sorted(named)} while the handshake names {sorted(NAMED_TOOLS)}"
    )
