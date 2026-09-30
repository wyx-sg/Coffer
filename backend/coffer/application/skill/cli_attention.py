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
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.skill.cli_requirements import CliRequirementService, CliView
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
        return [
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


__all__ = ["CliAttentionSource"]
