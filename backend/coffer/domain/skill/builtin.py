"""What makes a skill row Coffer's own rather than the user's.

One predicate over a raw config dict, in the domain because four different
layers have to ask it and none of them should re-derive the answer: the skill
kind (to refuse a delete and to withhold the row from sync), the seed (to find
the row it is about to rewrite), and the HTTP surface (to tell the UI the
folder is not editable).

It reads the raw mapping rather than a parsed :class:`~coffer.domain.skill
.config.SkillConfig` on purpose. Every caller asks it of a row that came out of
the database, possibly written by an older build, and a parse that raised on an
older shape would turn "is this Coffer's?" into an error where the honest
answer is "no".

**The skill's *name* is deliberately not here.** ``coffer-guide`` is a literal
in exactly two places that cannot import each other — the renderer that writes
it into the frontmatter (``application.knowledge.guide_render``) and the sync
slice that must not mirror its folder (``infrastructure.sync.paths``) — because
import-linter's cross-kind fences forbid both of them from reading
``coffer.domain.skill``. A constant here would be one more copy nobody could
use, so what lives here is the *property* instead, which is the thing the
resource framework actually reasons about: a builtin skill is one whose source
says so, whatever it happens to be called.
"""

from __future__ import annotations

from collections.abc import Mapping

#: The ``source.type`` discriminator of ``domain.skill.source.BuiltinSource``.
#: Spelled as a literal rather than instantiating the model, so this module
#: stays a pure predicate with no pydantic construction on a hot path.
BUILTIN_SOURCE_TYPE = "builtin"


def is_builtin(config: Mapping[str, object]) -> bool:
    """Whether a ``skill`` row's config marks it as Coffer's own.

    True means the master folder is written from the running build — rewritten
    at every boot and whenever the material it describes moves — which is what
    makes the row derived output rather than something the user authored.
    """
    source = config.get("source")
    return isinstance(source, Mapping) and source.get("type") == BUILTIN_SOURCE_TYPE


__all__ = ["BUILTIN_SOURCE_TYPE", "is_builtin"]
