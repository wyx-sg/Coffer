"""The two pure adapters over a ``Kind``'s optional config hooks.

Both answer "what does this kind say about a config dict?" without deciding
anything, and both are needed by more than one module in the resource
framework's cluster — which is why they sit here rather than inside
``resource_service.py``, where ``resource_delete_ops`` had to reach back in
through a function-local import to borrow one.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, validate_resource_name


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


def extract_credential_refs(kind_def: Kind, config: dict[str, Any]) -> dict[str, str]:
    """Return ``{key: credential_ref}`` for ``config`` using the kind's extractor.

    Kinds without a ``credential_ref_extractor`` declare no credentials and are
    not probed.
    """
    if kind_def.credential_ref_extractor is None:
        return {}
    return kind_def.credential_ref_extractor(config)


def check_name(kind_def: Kind, name: str) -> None:
    """Framework rule then kind rule, BEFORE any DB write.

    One helper because registration and rename must apply the same rules;
    while rename lived in one kind's service the two had already drifted —
    ``provider`` checked a length the framework did not and skipped the
    pattern the framework did.
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
