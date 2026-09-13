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

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.log_reader import matches_level, parse_log_line, tail_lines
from coffer.application.repos import AuditRepo

#: A debugging window, not an archive. An agent asking "what just happened"
#: means minutes, and a wide default would bury the relevant line.
_DEFAULT_SINCE_MINUTES = 60
_MAX_SINCE_MINUTES = 60 * 24 * 7

_DEFAULT_LIMIT = 40
_MAX_LIMIT = 200


def register_diagnostics_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    audit_repo: AuditRepo,
    log_path: Callable[[], Path],
) -> None:
    """Register ``diagnose`` (exposed as ``coffer__diagnose``)."""

    async def diagnose(args: dict[str, Any]) -> dict[str, Any]:
        since_minutes = min(
            max(int(args.get("since_minutes") or _DEFAULT_SINCE_MINUTES), 1),
            _MAX_SINCE_MINUTES,
        )
        limit = min(max(int(args.get("limit") or _DEFAULT_LIMIT), 1), _MAX_LIMIT)
        since = datetime.now(tz=UTC) - timedelta(minutes=since_minutes)
        errors_only = bool(args.get("errors_only"))

        entries = await audit_repo.query(
            kind=args.get("resource_kind") or None,
            name=args.get("resource_name") or None,
            event_type=args.get("event_type") or None,
            since=since,
            limit=limit,
        )
        changes = [
            {
                "at": e.timestamp.isoformat(),
                "event": e.event_type,
                "resource": (f"{e.resource_kind}:{e.resource_name}" if e.resource_kind else None),
                "actor": e.actor,
                "details": e.details,
            }
            for e in entries
        ]

        records: list[dict[str, Any]] = []
        for line in reversed(tail_lines(log_path())):
            if len(records) >= limit:
                break
            record = parse_log_line(line)
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
                            "Keep only error-level log records (and anything "
                            "unparseable, which is usually a traceback). The "
                            "audit side is unaffected."
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
                        "description": "Filter the audit side to one resource name.",
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
