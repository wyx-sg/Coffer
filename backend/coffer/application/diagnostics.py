"""``coffer__diagnose`` — Coffer's own history, read by the agent debugging it.

Coffer keeps two records of what it did: the **audit log** (what changed) and
the **daemon log** (what happened, including what broke). Neither had a reader.
The audit log had a web page nobody opened; the daemon log had to be found on
disk and grepped by hand.

The realistic reader of both is an agent, at the moment something has gone
wrong and the user has said "why". So this is an MCP tool rather than a page:
the agent already has it in hand, can ask without being told the file path, and
gets back something already correlated rather than two things to join.

**One question, two sources.** An agent that hits `CREDENTIAL_MISSING` does not
know whether it wants "what changed recently" or "what errored recently" — it
wants to know what happened. Asking for both and returning them on one timeline
is the difference between a tool that answers and a tool that needs a follow-up.

Read-only, and it never returns secret material: audit `details` are redacted by
each kind before they are stored, and log records carry no plaintext secret by
construction (see ``docs-site/architecture/observability.md``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.log_reader import matches_level, parse_log_lines, tail_lines
from coffer.application.repos import AuditRepo
from coffer.domain.resource import Resource

#: A debugging window, not an archive. An agent asking "what just happened"
#: means minutes, and a wide default would bury the relevant line.
_DEFAULT_SINCE_MINUTES = 60
_MAX_SINCE_MINUTES = 60 * 24 * 7

_DEFAULT_LIMIT = 40
_MAX_LIMIT = 200

#: ``(kind, name) -> the resource, or None`` when that kind has nothing by that
#: name. The audit log filters a resource's trail by its id, which is what makes
#: the trail survive a rename (ADR resource-identity-is-an-immutable-uid); the
#: agent asking knows a name, because a name is what it saw in a log line or an
#: error. This callable is where the two are reconciled — once, here, rather
#: than by teaching the audit query to take a label again.
ResourceFinder = Callable[[str, str], Awaitable[Resource | None]]


def register_diagnostics_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    audit_repo: AuditRepo,
    log_path: Callable[[], Path],
    find_resource: ResourceFinder | None = None,
) -> None:
    """Register ``diagnose`` (exposed as ``coffer__diagnose``).

    ``find_resource`` is what makes the ``resource_name`` filter work. Without
    it the filter is refused rather than ignored: silently dropping it would
    answer a question about one resource with every resource's history, which
    reads as "nothing else happened" — the opposite of the truth, at the one
    moment the agent is trying to establish what did.
    """

    async def diagnose(args: dict[str, Any]) -> dict[str, Any]:
        since_minutes = min(
            max(int(args.get("since_minutes") or _DEFAULT_SINCE_MINUTES), 1),
            _MAX_SINCE_MINUTES,
        )
        limit = min(max(int(args.get("limit") or _DEFAULT_LIMIT), 1), _MAX_LIMIT)
        since = datetime.now(tz=UTC) - timedelta(minutes=since_minutes)
        errors_only = bool(args.get("errors_only"))

        kind = str(args.get("resource_kind") or "").strip() or None
        name = str(args.get("resource_name") or "").strip() or None

        # A name is a label, and the audit log is filtered by the resource's
        # id — that is what keeps a renamed resource's history readable as one
        # history. So resolve the label to the row before asking. Every failure
        # here is raised, never swallowed: an unresolvable filter that fell
        # through would return the whole vault's recent history under a heading
        # the agent believes is one resource's.
        resource: Resource | None = None
        if name is not None:
            if kind is None:
                raise ValueError(
                    "'resource_name' needs 'resource_kind' beside it — a name is "
                    "unique only within its kind. Pass both, or drop the name and "
                    "filter by kind alone."
                )
            if find_resource is None:
                raise ValueError(
                    "this daemon cannot resolve a resource by name; filter by "
                    "'resource_kind' and 'event_type' instead."
                )
            resource = await find_resource(kind, name)
            if resource is None:
                raise ValueError(
                    f"no {kind} named {name!r} exists. Names are editable, so a name "
                    "from an older log line may since have changed; drop "
                    "'resource_name' to see everything that happened to this kind."
                )

        entries = await audit_repo.query(
            # With a resource resolved, its id is the whole filter: the kind is
            # already implied by it, and re-applying the kind would drop the
            # rows a kind-changing history never produces anyway.
            kind=None if resource is not None else kind,
            resource_id=resource.id if resource is not None else None,
            event_type=args.get("event_type") or None,
            since=since,
            limit=limit,
        )
        changes = [
            {
                "at": e.timestamp.isoformat(),
                "event": e.event_type,
                # Two fields, not one `<kind>:<name>` string: that string form
                # was Coffer's old identifier and is gone. Both are the LABEL
                # the resource carried when the event happened, which is the
                # point — a renamed resource's trail reads in the words that
                # were true at the time.
                "resource_kind": e.resource_kind,
                "resource": e.resource_name,
                "actor": e.actor,
                "details": e.details,
            }
            for e in entries
        ]

        records: list[dict[str, Any]] = []
        # Parse oldest-first — a traceback belongs to the record above it, not
        # to a record each — then walk backwards for a newest-first answer.
        for record in reversed(parse_log_lines(tail_lines(log_path()))):
            if len(records) >= limit:
                break
            if not matches_level(record, errors_only):
                continue
            at = str(record.get("timestamp", ""))
            # Cheap prefilter: ISO-8601 sorts lexically, so a string compare
            # is enough and costs no parsing per line.
            if at and at < since.isoformat():
                break
            records.append(record)

        return {
            "window_minutes": since_minutes,
            "changes": changes,
            "log": records,
            "note": (
                "changes = the audit log (what changed, and who changed it); "
                "log = the daemon log (what happened, including failures). "
                "Both newest-first. Neither carries secret values."
            ),
        }

    registry.register(
        BuiltinTool(
            name="diagnose",
            description=(
                "Read Coffer's own recent history when something has gone wrong "
                "with it — a tool call that failed, a credential that would not "
                "resolve, a server that stopped answering, an agent whose config "
                "changed under it. Returns two correlated timelines: what "
                "CHANGED (Coffer's audit log — registrations, deletions, "
                "credential reads, config writes, provider switches) and what "
                "HAPPENED (the daemon's own log, including errors and "
                "tracebacks). Use it before asking the user to go and find a log "
                "file; they cannot see one that Coffer can read for them. "
                "Read-only, and it returns no secret values."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "since_minutes": {
                        "type": "integer",
                        "default": _DEFAULT_SINCE_MINUTES,
                        "minimum": 1,
                        "maximum": _MAX_SINCE_MINUTES,
                        "description": "How far back to look. Start small.",
                    },
                    "errors_only": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Keep only error-level log records (and any line "
                            "whose level could not be read at all). A record's "
                            "traceback rides with it either way. The audit "
                            "side is unaffected."
                        ),
                    },
                    "event_type": {
                        "type": "string",
                        "description": (
                            "Filter the audit side to one event type, e.g. "
                            "'credential_read' or 'resource_deleted'."
                        ),
                    },
                    "resource_kind": {
                        "type": "string",
                        "description": "Filter the audit side to one kind, e.g. 'mcp_server'.",
                    },
                    "resource_name": {
                        "type": "string",
                        "description": (
                            "Filter the audit side to one resource, by its "
                            "current name. Requires 'resource_kind' — a name is "
                            "unique only within a kind. The resource's whole "
                            "trail comes back, including the rows written under "
                            "a name it no longer has."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "default": _DEFAULT_LIMIT,
                        "minimum": 1,
                        "maximum": _MAX_LIMIT,
                        "description": "Maximum entries per timeline.",
                    },
                },
            },
            handler=diagnose,
        )
    )


__all__ = ["register_diagnostics_builtin_tools"]
