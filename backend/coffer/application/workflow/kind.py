"""The ``workflow`` Kind for the composition root (spec workflow FR-001).

A template is a Resource and nothing else — no table of its own, no lifecycle
of its own. What it brings to the framework is one thing: a config that is a
whole program, validated by ``domain.workflow.template.parse_template`` and
refused with the JSON path of the offending field (FR-006).

The four flags, each for a reason:

- ``generic_create_allowed`` is **True**, unlike skill/knowledge/memory: a
  template has no directory, no master folder and no on-disk detection behind
  it, so the generic ``POST /resources`` path creates a complete resource. It
  is a document, and a document needs no lifecycle hook to be whole.
- ``supports_scope`` is True. A template's scope is read **inverted** — the
  agents this template may drive (FR-007) — and a node naming an agent outside
  it is refused by :func:`validate_template_agents` before the row is written.
- ``converges`` is True: a flow defined on one machine must be available on the
  developer's others (FR-008). It is the shape of the work, not a fact about a
  machine, which is exactly the line ``Kind.converges`` draws.
- ``on_delete`` is absent, and deliberately. A run froze its snapshot at
  creation (FR-010), so deleting a template cannot strand one; ``template_ref``
  is left dangling by design (data-model, "Deletion").
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any, Self

from pydantic import RootModel, model_validator

from coffer.domain.resource import Kind
from coffer.domain.workflow.errors import TemplateInvalid
from coffer.domain.workflow.template import parse_template

#: The kind name; ``workflow:<name>`` is a template's ref (FR-001).
KIND_WORKFLOW = "workflow"


class WorkflowTemplateConfig(RootModel[dict[str, Any]]):
    """The whole template definition, as the resource framework wants it.

    A ``RootModel`` for the same reason ``channel`` uses one: the config is a
    shape the domain already describes, and restating stages, nodes, artifacts
    and edges as Pydantic models would create a second definition of the
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
            # FR-006 that matters to whoever has to find the typo.
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
    framework's own rejection (FR-006, FR-007).
    """
    try:
        parse_template(config, known_skills=known_skills, allowed_agents=allowed_agents)
    except TemplateInvalid as exc:
        raise ValueError(str(exc)) from exc


def make_workflow_kind(
    *,
    known_skills: Collection[str] | None = None,
    allowed_agents: Collection[str] | None = None,
) -> Kind:
    """Build the ``workflow`` Kind.

    ``known_skills`` and ``allowed_agents`` are passed by the composition root
    when it can name them; ``None`` leaves that rule unchecked rather than
    guessing, which is what lets a test register a template without a skill
    registry behind it.
    """

    def _validate_config(config: dict[str, Any]) -> None:
        validate_template_agents(config, known_skills=known_skills, allowed_agents=allowed_agents)

    return Kind(
        name=KIND_WORKFLOW,
        display_name="Workflow",
        config_schema=WorkflowTemplateConfig,
        validate_config=_validate_config,
        generic_create_allowed=True,
        supports_scope=True,
        converges=True,
        # A template may be renamed (FR-054). Nothing addresses it by name
        # except a run's ``template_ref``, which is provenance and already
        # dangles when the template is deleted — so a rename leaves it saying
        # what the run was started from, which is what it was ever for.
        supports_rename=True,
    )
