"""Pydantic model for the SKILL.md frontmatter (agentskills.io).

The agentskills.io standard requires `name` and `description`: `name` is capped
at 64 chars (lowercase alphanumerics, hyphen, underscore) and `description` at
1024 chars. The optional fields `license` and the experimental `allowed-tools`
are recognized and retained; every other extra field is tolerated
(`extra="allow"`) so non-Coffer-authored skills validate cleanly. Coffer does
not act on a skill's body — the agent that loads it does — and it does not act
on `allowed-tools` either: the field is parsed so that round-tripping a skill's
frontmatter preserves it, and surfaced so a reader can see what a skill asks
for.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Capped at 64 chars to match the master store's folder-name limit
# (``master_store._NAME_MAX_LEN``). A longer name would pass schema validation
# here but then trip a bare ``ValueError`` inside ``copy_in`` → 500; aligning
# the cap turns it into a clean ``SkillValidationError`` (422) at validate time.
# Coffer accepts a documented superset of the agentskills.io name charset: the
# standard allows lowercase letters, digits, and hyphens, and Coffer also
# tolerates underscores for backward-compatibility with skills already on disk.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: A top-level ``name`` key in the frontmatter block — column 0, so a nested
#: mapping's own ``name`` is never mistaken for the skill's.
_NAME_KEY_RE = re.compile(r"^name[ \t]*:")

# agentskills.io caps the description at 1024 chars. Aligning the cap turns an
# over-long description into a clean ``SkillValidationError`` (422) at validate
# time instead of silently letting an out-of-spec skill into the master store.
_DESCRIPTION_MAX = 1024


class FrontmatterNameError(ValueError):
    """A proposed name is outside what a SKILL.md frontmatter may carry."""


def validate_frontmatter_name(name: str) -> None:
    """Raise :class:`FrontmatterNameError` unless ``name`` fits the standard.

    Exported so the `skill` Kind can hand it to the framework as its
    ``Kind.validate_name``, which every write path that sets a name — register
    AND rename — runs before persisting. That matters because the framework's
    own rule (``^[a-zA-Z0-9_.-]{1,64}$``) is LOOSER than this one: uppercase
    and dots pass there and would be legal as a directory, but a skill's name
    is also written into its SKILL.md, and a file Coffer wrote must be one
    Coffer's own validator would accept on the next import.

    Registration already satisfied this rule implicitly — the resource's name
    is *derived* from the frontmatter it just validated — so declaring it here
    narrows nothing that exists; it closes the rename path, which had no
    kind-level check at all.
    """
    if not _NAME_RE.match(name):
        raise FrontmatterNameError(
            f"invalid skill name {name!r}: must match {_NAME_RE.pattern} "
            "(lowercase letters, digits, hyphen, underscore)"
        )


def rewrite_name(text: str, new_name: str) -> str | None:
    """Return ``text`` with the frontmatter's ``name:`` set to ``new_name``.

    Returns ``None`` when there is no frontmatter block, or no top-level
    ``name`` key inside it, to rewrite — the caller decides what that means.

    Surgical on purpose: exactly one line changes and every other byte of the
    document survives, including its line endings, the key order, comments,
    and any field this model does not model. Re-serialising the parsed
    frontmatter would be far shorter and would silently reflow a file the user
    writes by hand and edits in Coffer's own editor — dropping their comments
    and reordering their keys as a side effect of a rename.

    ``_parse_frontmatter`` in the validator cannot be reused: it hands back
    parsed YAML, and this needs to know WHICH LINE to touch.

    ``new_name`` is assumed to have passed :func:`validate_frontmatter_name`,
    which is what makes plain ``name: <value>`` safe to emit without quoting.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        stripped = lines[i].strip()
        if stripped == "---":
            return None  # reached the end of the block without finding `name`
        # A top-level key starts at column 0; an indented `name:` belongs to
        # some nested mapping and is not the skill's own name.
        if _NAME_KEY_RE.match(lines[i]):
            ending = lines[i][len(lines[i].rstrip("\r\n")) :]
            lines[i] = f"name: {new_name}{ending}"
            return "".join(lines)
    return None


class SkillFrontmatter(BaseModel):
    """The frontmatter block at the top of `SKILL.md`."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=_DESCRIPTION_MAX)
    license: str | None = None
    allowed_tools: list[str] | None = Field(default=None, alias="allowed-tools")

    @field_validator("license", mode="before")
    @classmethod
    def _coerce_license(cls, v: Any) -> str | None:
        """Tolerate any scalar `license` value by stringifying it.

        YAML parses an unquoted scalar by type, so `license: 2024` (int),
        `license: true` (bool), or `license: 1.0` (float) would otherwise
        reject the whole skill under a strict `str`. Recognizing optional
        fields is additive (FR-005), so coerce scalars to a string and
        tolerate any non-scalar shape as absent rather than failing.
        """
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, (int, float, bool)):
            return str(v)
        return None

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        # One rule, one message: the kind's ``validate_name`` runs the same
        # function, so parsing a file and renaming a row cannot disagree about
        # what a legal skill name is.
        validate_frontmatter_name(v)
        return v

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _coerce_allowed_tools(cls, v: Any) -> list[str] | None:
        """Normalize the experimental `allowed-tools` field to a list of names.

        The field is experimental and third-party authored, so be lenient:
        accept a YAML list or a comma/whitespace-separated string, drop blanks,
        and tolerate any other shape by returning ``None`` rather than rejecting
        an otherwise-valid skill.
        """
        if v is None:
            return None
        if isinstance(v, str):
            parts = [p.strip() for p in re.split(r"[,\s]+", v)]
            return [p for p in parts if p] or None
        if isinstance(v, (list, tuple)):
            normalized = [str(p).strip() for p in v]
            return [p for p in normalized if p] or None
        return None
