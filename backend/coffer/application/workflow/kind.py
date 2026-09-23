"""The ``workflow`` Kind for the composition root (spec workflow
"Register a template as a workflow resource").

A template is a Resource and nothing else — no table of its own, no lifecycle
of its own. What it brings to the framework is one thing: a config that is a
whole program, validated by ``domain.workflow.template.parse_template`` and
refused with the JSON path of the offending field ("Refuse an invalid
template naming the offending path").

The four flags, each for a reason:

- ``generic_create_allowed`` is **True**, unlike skill/knowledge/memory: a
  template has no directory, no master folder and no on-disk detection behind
  it, so the generic ``POST /resources`` path creates a complete resource. It
  is a document, and a document needs no lifecycle hook to be whole.
- ``supports_scope`` is True. A template's scope is read **inverted** — the
  agents this template may drive ("Read a template's scope as the agents it
  may drive") — and a node naming an agent outside it is refused before the
  row is written, on both write paths: an edit to the config is checked
  against the scope the template has, and an edit to the scope against the
  config it has.
- ``converges`` is True: a flow defined on one machine must be available on the
  developer's others ("Sync templates with the vault"). It is the shape of the
  work, not a fact about a machine, which is exactly the line
  ``Kind.converges`` draws.
- ``on_delete`` is absent, and deliberately. A run froze its snapshot at
  creation ("Freeze the template when a run is created"), so deleting a
  template cannot strand one; ``template_ref`` is left dangling by design
  (data-model, "Deletion").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable
from typing import Any, Self

from pydantic import RootModel, model_validator

from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, Resource
from coffer.domain.scope import Scope
from coffer.domain.workflow.errors import TemplateInvalid
from coffer.domain.workflow.template import parse_template

#: The kind name. A template is addressed by the framework's uid like every
#: other resource (spec workflow "Register a template as a workflow
#: resource"); this is only what the row's ``kind`` column says.
KIND_WORKFLOW = "workflow"


class WorkflowTemplateConfig(RootModel[dict[str, Any]]):
    """The whole template definition, as the resource framework wants it.

    A ``RootModel`` for the same reason ``channel`` uses one: the config is a
    shape the domain already describes, and restating stages, nodes and their
    artifacts as Pydantic models would create a second definition of the
    template that could drift from the one that runs. Validation accepts the
    flat config dict and ``model_dump`` returns it unchanged, so what is stored
    is what the developer wrote.
    """

    @model_validator(mode="after")
    def _parse(self) -> Self:
        try:
            parse_template(self.root)
        except TemplateInvalid as exc:
            # Re-raised as a ValueError so Pydantic folds it into the
            # ValidationError the framework already turns into a 422. The
            # message still leads with the JSON path, which is the half of
            # spec workflow "Refuse an invalid template naming the
            # offending path" that matters to whoever has to find the
            # typo.
            raise ValueError(str(exc)) from exc
        return self


def validate_template_agents(
    config: dict[str, Any],
    *,
    known_skills: Collection[str] | None = None,
    allowed_agents: Collection[str] | None = None,
) -> None:
    """The two rules the config schema cannot answer alone.

    Whether a skill is registered and whether an agent is inside this
    template's scope are facts about the vault, not about the document, so they
    are checked where the vault is reachable. Raised as ``ValueError`` because
    that is what the ``Kind.validate_config`` seam converts into the
    framework's own rejection (spec workflow "Refuse an invalid template naming
    the offending path", "Read a template's scope as the agents it may drive").
    """
    try:
        parse_template(config, known_skills=known_skills, allowed_agents=allowed_agents)
    except TemplateInvalid as exc:
        raise ValueError(str(exc)) from exc


#: The agent row's config key holding the key the turn platform runs it by —
#: the vocabulary a node's ``agent`` is written in.
_AGENT_KEY = "type"

#: Every registered agent resource, read when a scope has to be compared.
AgentRows = Callable[[], Awaitable[Iterable[Resource]]]


async def _scope_as_agent_keys(scope: Scope | None, agents: AgentRows) -> set[str] | None:
    """The agent keys ``scope`` admits, or ``None`` when it admits every agent.

    A scope names agents by uid and a node names one by key, so the two meet
    here. A uid no registered agent carries admits nothing: dropping it only
    narrows what the template may drive, never widens it.
    """
    if scope is None or scope.agents is None:
        return None
    keys_by_uid = {
        row.uid: key
        for row in await agents()
        if isinstance(key := row.config.get(_AGENT_KEY), str) and key
    }
    return {keys_by_uid[uid] for uid in scope.agents if uid in keys_by_uid}


def make_workflow_kind(
    *,
    known_skills: Collection[str] | None = None,
    allowed_agents: Collection[str] | None = None,
    agents: AgentRows | None = None,
) -> Kind:
    """Build the ``workflow`` Kind.

    ``known_skills`` and ``allowed_agents`` are passed by the composition root
    when it can name them; ``None`` leaves that rule unchecked rather than
    guessing, which is what lets a test register a template without a skill
    registry behind it.

    ``agents`` reads the registered agent rows. Given, it holds a template to
    its own scope (spec workflow "Read a template's scope as the agents it may
    drive") on the two paths that can break that: a config edit is checked
    against the scope the row has, and a scope edit against the config it has.
    Registration needs neither — a new row carries no scope yet.
    """

    def _validate_config(config: dict[str, Any]) -> None:
        validate_template_agents(config, known_skills=known_skills, allowed_agents=allowed_agents)

    async def _check_update(resource: Resource, after: dict[str, Any]) -> None:
        assert agents is not None
        allowed = await _scope_as_agent_keys(resource.scope, agents)
        try:
            validate_template_agents(after, known_skills=known_skills, allowed_agents=allowed)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

    async def _check_scope(resource: Resource, scope: Scope | None) -> None:
        # ``ValueError`` is what the framework turns into SCOPE_INVALID.
        assert agents is not None
        allowed = await _scope_as_agent_keys(scope, agents)
        validate_template_agents(resource.config, allowed_agents=allowed)

    return Kind(
        name=KIND_WORKFLOW,
        display_name="Workflow",
        config_schema=WorkflowTemplateConfig,
        validate_config=_validate_config,
        on_update_config=_check_update if agents is not None else None,
        validate_scope_for=_check_scope if agents is not None else None,
        generic_create_allowed=True,
        supports_scope=True,
        converges=True,
    )
