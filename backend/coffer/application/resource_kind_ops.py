"""What a kind declares about itself, asked of the registry.

Extracted to keep ``resource_service.py`` under the file-size limit, the same
way ``resource_scope_ops`` and ``resource_delete_ops`` were — but unlike those
two this is not one mutation path. It is the whole of the read side of the kind
registry: every place the kind-agnostic core has to consult a kind's
*declaration* rather than act on a row.

Five questions, and they belong together because they are one shape. Each takes
the registry and a kind name (or a ``Kind`` the caller already resolved), reads
a field the kind set when it was built, and answers. None of them touches the
repository, the audit log or a resource; none of them can fail a write. The
service keeps thin delegates so callers see no change.

Free functions over the registry rather than methods, because two of them —
``audit_safe_config`` and ``secret_refs`` — were already free functions
taking a resolved ``Kind``, and nothing here needs the service at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, normalise_title, validate_resource_name
from coffer.domain.vault.layout import StorageClass

Registry = Mapping[str, Kind]


def audit_safe_config(kind_def: Kind, config: dict[str, Any]) -> dict[str, Any]:
    """Return an audit-safe copy of ``config`` using the kind's redactor.

    The kind-agnostic core knows nothing about where a given kind stores
    secrets; each kind supplies its own ``audit_redactor`` (e.g. mcp_server
    strips ``transport.env``/``headers``). Kinds without one audit their
    config verbatim. See the resource-framework-upfront ADR.
    """
    if kind_def.audit_redactor is None:
        return config
    return kind_def.audit_redactor(config)


def secret_refs(kind_def: Kind, config: dict[str, Any]) -> dict[str, str]:
    """Return ``{key: secret_ref}`` for ``config`` using the kind's extractor.

    Kinds without a ``secret_ref_extractor`` declare no secrets and are
    not probed.
    """
    if kind_def.secret_ref_extractor is None:
        return {}
    return kind_def.secret_ref_extractor(config)


def storage_of(kinds: Registry, kind: str, config: Mapping[str, Any]) -> StorageClass:
    """The storage class a new resource of ``kind`` with ``config`` is filed in
    (ADR storage-is-five-classes-by-nature): the kind's ``storage`` refined by
    its per-row ``storage_row``.

    An unregistered kind answers ``vault``: the vault is where a person's
    resources live, and a kind this build does not know (a newer build's) is
    kept there, inert, rather than guessed into a class that would not travel.
    """
    kind_def = kinds.get(kind)
    if kind_def is None:
        return StorageClass.VAULT
    if kind_def.storage_row is not None:
        return kind_def.storage_row(dict(config))
    return kind_def.storage


def check_name(kind_def: Kind, name: str) -> None:
    """Framework rule then kind rule, BEFORE any DB write.

    One helper because registration and rename must apply the same rules;
    while rename lived in one kind's service the two had already drifted —
    ``provider`` checked a length the framework did not and skipped the
    pattern the framework did.

    The one question here that can raise. It still asks only what the kind
    *declares*, and still never touches a row: what it refuses is the argument
    a caller is about to write, not the state of the vault.
    """
    try:
        validate_resource_name(name)
    except ValueError as e:
        raise ConfigValidationError(str(e)) from e
    # Kind-specific name validation (e.g. mcp_server reserves '__'
    # as the tool/prompt namespace separator; skill enforces the SKILL.md
    # frontmatter charset, which is stricter than the framework's).
    if kind_def.validate_name is not None:
        try:
            kind_def.validate_name(name)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e


def checked_title(kind_def: Kind, title: str | None) -> str | None:
    """The title to store — ``None`` for a blank one — or ``ConfigValidationError``
    for one over the cap, or for any title on a kind that carries none
    (``Kind.titled``), before any write."""
    try:
        wanted = normalise_title(title)
    except ValueError as e:
        raise ConfigValidationError(str(e)) from e
    if wanted is not None and not kind_def.titled:
        raise ConfigValidationError(
            f"the {kind_def.name} kind carries no title: it is shown by its name, which is fixed"
        )
    return wanted


def check_derived_name(kind_def: Kind, name: str, config: dict[str, Any]) -> None:
    """Refuse a name other than the one the kind derives from ``config``
    (``Kind.name_from_config``) — an agent is named by its type."""
    if kind_def.name_from_config is None:
        return
    wanted = kind_def.name_from_config(config)
    if name != wanted:
        raise ConfigValidationError(
            f"the name of this {kind_def.name} is its type's: it must be {wanted!r}, not {name!r}"
        )


__all__ = [
    "Registry",
    "audit_safe_config",
    "check_derived_name",
    "check_name",
    "checked_title",
    "secret_refs",
    "storage_of",
]
