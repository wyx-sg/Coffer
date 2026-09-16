"""What a kind's audit redactor is allowed to write down.

The audit log is durable and readable by anyone who can reach the daemon, so a
secret that reaches it is a secret leaked for as long as the entry is retained.
Redaction is per-kind: the kind-agnostic `ResourceService` knows nothing about
a transport's shape, so each kind supplies its own redactor and is responsible
for the fields only it understands.
"""

from __future__ import annotations


def test_mcp_audit_redactor_strips_transport_env_and_headers() -> None:
    """A transport's `headers` (and `env`) carry bearer tokens verbatim and must
    never be audited; `credential_refs` are NAMES, not values, and must survive
    — they are how an operator later works out which credential a server used.

    The redactor must also not mutate its input: it runs on the live config
    object on its way to the DB, so an in-place strip would silently delete the
    caller's headers.
    """
    from coffer.application.mcp.kind import _mcp_audit_redactor

    cfg = {
        "transport": {
            "type": "http",
            "url": "https://example/mcp",
            "headers": {"Authorization": "Bearer secret123"},
            "credential_refs": {"X-Api-Key": "mykey"},
        },
    }
    sanitised = _mcp_audit_redactor(cfg)
    assert "headers" not in sanitised["transport"]
    assert sanitised["transport"]["credential_refs"] == {"X-Api-Key": "mykey"}
    # Original input must not be mutated.
    assert "headers" in cfg["transport"]
