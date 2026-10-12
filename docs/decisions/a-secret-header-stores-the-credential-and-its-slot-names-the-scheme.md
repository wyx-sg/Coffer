# A Secret Header Stores the Credential Alone, and Its Slot Names the Auth Scheme

**Status**: Accepted
**Date**: 2026-10-05
**Deciders**: Yuxing Wu
**Related**: [Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), spec mcp-gateway ("Support stdio and HTTP upstreams"), spec web-ui ("Choose secrets in one field and one set of rows"), research note [credentials and secrets](../research/credentials-secrets.md) §8, PR #585

## Context

An HTTP MCP server and a custom-tool group authenticate with a header, and the
header's value comes from a secret the config cites by reference
([Resources Cite Secrets by Opaque Reference](credential-references.md)): a
`secret_refs` map of header name to ref. What, exactly, does the secret hold?

A provider hands out a bare key. HTTP sends it in one of three shapes:
`Authorization: Bearer <key>`, `Authorization: Token <key>` (GitHub's older
tokens, several self-hosted APIs), or the key alone in a header such as
`X-Api-Key`. The secret store is shared across uses: the same key may be
injected into an MCP server's header, a custom tool's header, a stdio server's
environment, or a `coffer run` child
([Standalone Secrets](standalone-secrets-are-named-references-injected-into-one-child.md)),
and only the header case has a scheme.

Before PR #585 a secret header stored the whole header value. A person who
created a secret from the key their provider gave them and bound it to
`Authorization` sent `Authorization: <key>`, and the upstream answered 401 —
the normal setup failed, and the fix (re-entering the secret as
`Bearer <key>`) left a value that was wrong everywhere else it was used.
Values also arrive already prefixed: an agent's own MCP entry adopted into
Coffer, the plaintext import moving a literal header into the store, a value
pasted into a form.

## Options Considered

### Option A — Store the credential alone; the slot names the scheme, added at send time (chosen)

The secret holds only the key. Each secret header's slot may carry a scheme,
`Bearer` or `Token` (`auth_schemes`, keyed by header name), allowed only on a
header that cites a secret. At injection the gateway sends
`<scheme> <credential>`, or the credential alone for a slot without a scheme
(`domain/auth_scheme.py`: `header_value`, `with_schemes`). A value that arrives
as `Bearer <key>` or `Token <key>` — adopted, imported or pasted — is split into
the key and the scheme before it is stored (`split_scheme`). A new
`Authorization` row defaults to Bearer.

Pros: the secret is what the provider issued, so it can be created from the
provider's page as is and reused in any header, environment variable or child
process; the scheme is visible and editable in the config, not hidden inside
ciphertext; secret-scanning and the plaintext guard see one canonical value.
A slot without a scheme behaves exactly as before, so existing configs needed
no migration.

Cons: one more field per header; a header whose scheme is neither Bearer nor
Token (`Basic`, a vendor's own word) must be stored whole on a slot without a
scheme.

Wins because it makes the common setup work on the first try and keeps one
secret usable everywhere, at the cost of a small, closed field.

### Option B — Store the whole header value (the design this replaced)

The secret holds `Bearer <key>`, exactly what goes on the wire.

Pros: no scheme field; any scheme, including unusual ones, works by
construction; matches Claude Code's `.mcp.json` `headers`, which take a literal
value with `${VAR}` expansion.

Cons: the stored secret is bound to one header's syntax. A key entered as the
provider issued it fails with a 401; the same key used in an environment
variable or a second header must be stored again in another shape, so one
credential becomes two secrets that rotate separately. The scheme is
invisible: a reader of the config cannot tell what is being sent.

Loses on the incident that prompted PR #585: the normal path failed.

### Option C — Guess the scheme from the header name

Send `Bearer <key>` whenever the header is `Authorization`, the bare key
otherwise.

Pros: no field and no choice for the person in the common case.

Cons: wrong for every `Authorization: Token …` API and for an `Authorization`
header that wants the bare key; a wrong guess fails at the upstream with no
way to correct it short of a code change.

Loses because the guess cannot be overridden.

### Option D — A full auth-type model (Bearer, Basic, API key in header or query, OAuth)

Model authentication the way Postman's auth types or an OpenAPI
`securitySchemes` entry do, one type per request.

Pros: covers Basic and query-string keys; familiar from API tools.

Cons: much more surface than an MCP header needs; OAuth for MCP is a
separate, standardised flow; a key in a query string is the injection site the
redirect rule is hardest to keep safe for
([Security](../../docs-site/architecture/security.md#outbound-requests)).

Loses because the two schemes in use cover the servers people register, and a
slot without a scheme already carries anything else.

## Decision

A secret header — on an HTTP MCP server or a custom-tool group — stores only
the credential. Its slot may name an auth scheme, `Bearer` or `Token`, in
`auth_schemes`, allowed only on a header that cites a secret; the scheme is put
in front of the credential at injection, and a slot without a scheme sends the
stored value as it is. Every path that brings in a prefixed value splits it
into the key and the scheme before storing.

Rules a future change must respect:

- A secret's value is the credential as issued, never a value shaped for one
  header.
- A new scheme is a new member of the closed `AuthScheme` set, not free text.
- A scheme lives in the config beside the ref, never inside the ciphertext.

## Consequences

- One secret serves an MCP header, a custom tool, a stdio environment and a
  `coffer run` child without being stored twice.
- Headers with other schemes (`Basic …`) work only stored whole on a slot
  without a scheme; the form says nothing about them.
- Enforced by: `domain/auth_scheme.py` (`header_value`, `split_scheme`,
  `check_schemes`), the server and custom-tool config models
  (`domain/mcp/server_config.py`, `domain/mcp/http_api.py`), the HTTP clients
  that inject (`infrastructure/mcp/http_client.py`,
  `infrastructure/mcp/http_api_client.py`), and the import paths that split a
  prefixed value (`application/secret/plaintext_move.py`,
  `application/agent/mcp_adopt_secrets.py`); `tests/unit/domain/mcp/test_auth_scheme.py`.
