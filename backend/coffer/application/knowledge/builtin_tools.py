"""The knowledge layer's one built-in MCP tool.

``coffer__write`` — and nothing else (spec knowledge FR-033). ``list``,
``grep``, ``read``, ``search`` and ``delete`` are gone.

**Why reading has no tool.** Across 448 Claude Code sessions after the corpus
was built, the delivered skill was never loaded once and no knowledge tool was
ever called. The question was never which retrieval mechanism to expose: a
tool an agent does not remember to call is not retrieval. Every agent Coffer
supports already has `Read` and `Grep`, which need no remembering, so the
layer's job narrows to putting the right absolute paths in front of the model —
which the delivered skill does, catalogue and all (FR-037).

**Why writing keeps one.** A write is the one operation where the agent
genuinely needs Coffer rather than a filesystem: which collections exist, which
lane the file belongs in, what frontmatter it carries, and the audit entry
naming who wrote it are all this layer's to decide. It is also the only
remaining place an invocation is recorded.

The tool's description is one of exactly two places this layer is always in a
model's context (the other is the gateway's own instructions), so it says what
writing here is *for* rather than describing an API.
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.entry import KnowledgeFile
from coffer.domain.knowledge.errors import CollectionNotFound

#: Audit actor for an agent-side write when the session reported no identity.
_ANONYMOUS_ACTOR = "agent"


def _text(value: Any) -> str:
    """A trimmed string, or empty for anything that is not usable text."""
    return value.strip() if isinstance(value, str) else ""


def _required(args: dict[str, Any], name: str) -> str:
    value = _text(args.get(name))
    if not value:
        raise ValueError(f"{name!r} must be a non-empty string")
    return value


def _agent(args: dict[str, Any]) -> str | None:
    """The session's agent identity, or ``None`` when it reported none.

    Set by the gateway, never by the caller: it is absent from the tool's input
    schema and overwritten on every call (spec mcp-gateway FR-013). It narrows
    nothing — every enabled collection is writable by every agent — and is read
    for exactly one reason: the audit entry naming who wrote the file. ``None``
    becomes :data:`_ANONYMOUS_ACTOR` there, because an unattributed write is
    still worth recording.
    """
    return _text(args.get("agent")) or None


def _payload(file: KnowledgeFile) -> dict[str, Any]:
    return {
        "path": file.path,
        "title": file.title,
        "description": file.description,
        "file_path": file.file_path,
        "folder_path": file.folder_path,
    }


def register_knowledge_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    knowledge_service: KnowledgeService,
) -> None:
    """Wire the one knowledge tool into the gateway's registry."""

    svc = knowledge_service

    async def write(args: dict[str, Any]) -> dict[str, Any]:
        agent = _agent(args)
        try:
            written = await svc.write_source(
                title=_required(args, "title"),
                description=_required(args, "description"),
                # Optional, matching the REST surface and FR-014: a file whose
                # whole content is its title and description is a legitimate
                # thing to write, and rejecting it would be a rule only one of
                # the two write surfaces had.
                body=_text(args.get("body")),
                collection=_required(args, "collection"),
                folder=_text(args.get("folder")) or None,
                actor=agent or _ANONYMOUS_ACTOR,
            )
        except CollectionNotFound as exc:
            # Name the enabled collections. It is not a second retrieval
            # surface: it discloses exactly what the delivered skill already
            # lists, and it turns a dead end into a correction for a model that
            # reached for the tool without having opened the skill.
            enabled = await svc.enabled_collections()
            raise ValueError(
                f"no collection named {exc.name!r} is available to you. "
                + (f"You may write to: {', '.join(enabled)}." if enabled else "You have none.")
            ) from exc
        return {
            **_payload(written),
            "status": "written",
            "note": (
                "Filed as source material. Coffer's curation pass folds it into this "
                "collection's topic documents shortly; it will not stay at this path "
                "verbatim."
            ),
        }

    registry.register(
        BuiltinTool(
            name="write",
            description=(
                "Record something durable about this user's working environment "
                "into Coffer's knowledge — a fact about a service, a convention "
                "they follow, a decision and its reason, a trap and how to avoid "
                "it. What you write is filed as source material: Coffer's own "
                "model then merges it into the collection's topic documents, "
                "deduplicating against what is already there, so write the fact "
                "plainly and do not worry about where it belongs or whether it "
                "repeats something. Not for what is already in the repository in "
                "front of you, not for anything transient to this session, and "
                "never for secrets. To READ this knowledge, use your own file "
                "tools at the paths the coffer-knowledge skill lists — there is "
                "no read tool here."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": (
                            "Which collection to file it under. The "
                            "coffer-knowledge skill names them all."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Human-readable title naming the subject.",
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "One line saying what this answers. Required: it is "
                            "what curation reads first when deciding where the "
                            "material belongs."
                        ),
                    },
                    "body": {"type": "string", "description": "The Markdown content."},
                    "folder": {
                        "type": "string",
                        "description": (
                            "Optional folder inside the collection's sources to file it under."
                        ),
                    },
                },
                "required": ["collection", "title", "description"],
            },
            handler=write,
        )
    )
