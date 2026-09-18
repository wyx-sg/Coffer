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
``audit_safe_config`` and ``credential_refs`` — were already free functions
taking a resolved ``Kind``, and nothing here needs the service at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, validate_resource_name

Registry = Mapping[str, Kind]


def audit_safe_config(kind_def: Kind, config: dict[str, Any]) -> dict[str, Any]:
    """Return an audit-safe copy of ``config`` using the kind's redactor.

    The kind-agnostic core knows nothing about where a given kind stores
    secrets; each kind supplies its own ``audit_redactor`` (e.g. mcp_server
    strips ``transport.env``/``headers``). Kinds without one audit their
    config verbatim. See the resource-framework-upfront ADR / CODE-006.
    """
    if kind_def.audit_redactor is None:
        return config
    return kind_def.audit_redactor(config)


def credential_refs(kind_def: Kind, config: dict[str, Any]) -> dict[str, str]:
    """Return ``{key: credential_ref}`` for ``config`` using the kind's extractor.

    Kinds without a ``credential_ref_extractor`` declare no credentials and are
    not probed.
    """
    if kind_def.credential_ref_extractor is None:
        return {}
    return kind_def.credential_ref_extractor(config)


def converges(kinds: Registry, kind: str) -> bool:
    """Whether this kind's rows travel to the sync remote (spec vault-sync).

    Public on the service for the same reason ``supports_scope`` is: the sync
    layer has to ask, and the answer belongs to the kind.

    An unregistered kind answers **True**, which is the conservative answer
    and not the obvious one. This flag exists only to withhold, so a kind
    nobody has declared anything about must keep whatever behaviour it had:
    an unknown kind arriving in a document still reaches ``register`` and is
    still refused there by name (``UnknownKind``). Answering False would have
    turned that named refusal into a silent skip — a document quietly doing
    nothing is exactly what a converge round must not produce.
    """
    kind_def = kinds.get(kind)
    return kind_def.converges if kind_def is not None else True


def converges_row(kinds: Registry, kind: str, config: Mapping[str, Any]) -> bool:
    """Whether **this one row** travels to the sync remote (spec vault-sync).

    The kind-level answer refined by the kind's own per-row predicate. A kind
    that declares nothing answers exactly as :func:`converges` does, so this is
    the question the sync layer should ask everywhere — there is no case where
    "the kind travels" is the right answer but "this row travels" is not asked.

    Note what it is **not**: it is not the machine-local kind list the
    exporter's header refuses to reintroduce. That list was a table in the sync
    layer naming kinds it had opinions about, so the sync layer had to be
    edited whenever a kind changed its mind, and it could only ever speak about
    a kind as a whole. This is the opposite direction — the kind still
    declares, and the sync layer still only asks; all that has widened is the
    granularity of what a kind may declare. The answer comes out of the row's
    own config, so no name and no table appears in the sync slice at all.

    ``config`` is accepted as a plain mapping because the sync applier asks
    this of a document that has just arrived and has no row behind it yet; the
    predicate reads raw keys and never parses, so a shape an older build wrote
    answers rather than raising.
    """
    kind_def = kinds.get(kind)
    if kind_def is None:
        return True
    if not kind_def.converges:
        return False
    if kind_def.converges_row is None:
        return True
    return kind_def.converges_row(dict(config))


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
    # CODE-030: kind-specific name validation (e.g. mcp_server reserves '__'
    # as the tool/prompt namespace separator; skill enforces the SKILL.md
    # frontmatter charset, which is stricter than the framework's).
    if kind_def.validate_name is not None:
        try:
            kind_def.validate_name(name)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e


__all__ = [
    "Registry",
    "audit_safe_config",
    "check_name",
    "converges",
    "converges_row",
    "credential_refs",
]
