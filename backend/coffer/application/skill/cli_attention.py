"""What about the commands skills require needs a person (the Overview list).

One item per command that is ``missing``, ``outdated`` or ``logged_out``
(reason codes ``cli_missing``, ``cli_outdated``, ``cli_logged_out``), kind
``cli`` with the command as the uid, each a warning whose action is ``check``
— the CLIs page's own Check again — and the CLIs page's hand-off prompt
(which names the login command for a command that is not logged in, so the
reason names none). A command only MCP servers need (a stdio launcher no
skill declares) raises no item here: the server's own ``mcp_missing_launcher``
item already names it. It reads the service's cache, probing only
commands nothing was checked for yet.

A skill with a secret it requires that is not set raises one item naming every
such secret: kind ``skill`` with the skill's uid, reason
``skill_missing_secret``, and the Secrets page's own write as its action, with
the first secret's ref and no value — setting a secret is the person's task, so
it carries no hand-off (spec skill-manager "Report a secret a skill requires
that is not set").
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.skill.cli_requirements import (
    CliRequirementService,
    CliView,
    MissingSecret,
)
from coffer.domain.secrets import secret_ref
from coffer.domain.skill.cli_status import CliStatus

KIND = "cli"


def _reason(view: CliView) -> str:
    row, probe = view.required, view.probe
    skills = ", ".join(n.skill_name for n in row.needed_by)
    if view.status is CliStatus.MISSING:
        return f"{row.command} is not on the agent's PATH; needed by {skills}."
    if view.status is CliStatus.OUTDATED:
        return f"{row.command} {probe.version} is older than {row.min_version}, needed by {skills}."
    return f"{row.command} is not logged in; needed by {skills}."


class CliAttentionSource:
    name = KIND
    feature: str | None = None

    def __init__(self, service: CliRequirementService) -> None:
        self._service = service

    async def items(self) -> Sequence[AttentionItem]:
        listing = await self._service.listing()
        commands = [
            AttentionItem(
                kind=KIND,
                uid=view.required.command,
                title=view.required.title or view.required.command,
                reason_code=f"cli_{view.status.value}",
                reason=_reason(view),
                severity=Severity.WARNING,
                action=AttentionAction(
                    verb="check",
                    method="POST",
                    path=f"/api/v1/clis/{view.required.command}/check",
                ),
                handoff=view.handoff,
            )
            for view in listing.items
            if view.status is not CliStatus.READY and view.required.needed_by
        ]
        return commands + _secret_items(await self._service.missing_secrets())


def _secret_items(missing: Sequence[MissingSecret]) -> list[AttentionItem]:
    """One item per skill (the list keys an item by kind, uid and reason),
    naming every secret of it that is not set."""
    by_skill: dict[str, list[MissingSecret]] = {}
    for m in missing:
        by_skill.setdefault(m.skill_uid, []).append(m)
    return [_secret_item(group) for group in by_skill.values()]


def _secret_item(group: Sequence[MissingSecret]) -> AttentionItem:
    first = group[0]
    unset = "; ".join(f"secret {m.secret} is not set" for m in group)
    return AttentionItem(
        kind="skill",
        uid=first.skill_uid,
        title=first.skill_name,
        reason_code="skill_missing_secret",
        reason=f"{unset}; the skill requires {'it' if len(group) == 1 else 'them'}.",
        severity=Severity.WARNING,
        # The Secrets page's own write, with the ref and no value: the person
        # supplies the secret there.
        action=AttentionAction(
            verb="set_secret",
            method="POST",
            path="/api/v1/secrets",
            body={"ref": secret_ref(first.secret)},
        ),
    )


__all__ = ["CliAttentionSource"]
