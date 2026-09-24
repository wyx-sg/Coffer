---
title: Security policy
description: How to report a vulnerability in Coffer privately, what to include and what response to expect, and the security invariants every code change must respect.
---

# Security policy

This page has two audiences. If you found a vulnerability, the first half tells you how to report it privately. If you are changing Coffer's code, the second half lists the security invariants your change must keep. For the threat model and how the protections fit together, read the [security model](/architecture/security).

## Reporting a vulnerability

::: danger Do not open a public issue
Never report a security finding in a public GitHub issue, discussion or pull request.
:::

Use one of these private channels:

1. **GitHub private vulnerability reporting** (preferred). Open a report at [github.com/wyx-sg/Coffer/security/advisories/new](https://github.com/wyx-sg/Coffer/security/advisories/new), or use **Report a vulnerability** on the repository's Security tab. You need to be signed in to GitHub.
2. **Email** the maintainer at [hutwyx@gmail.com](mailto:hutwyx@gmail.com). Encrypt it with the maintainer's public PGP key if you have it. Plain text is acceptable for non-critical findings.

### What to include

- The affected commit or version.
- Steps to reproduce: a minimal setup and the relevant log excerpt.
- Your assessment of the impact.
- A suggested mitigation, if you have one.

### What to expect

| Step | Target |
| --- | --- |
| Acknowledgement | Within 72 hours |
| Triage and first response | Within 7 days |
| Fix and disclosure timeline | Agreed case by case, typically 30 to 90 days |

Coffer is pre-1.0 and has a single maintainer, so these times are best effort, not a guaranteed SLA.

### Supported versions

Only `main` is supported. Fixes land on `main` and ship in the next release. Older versions receive no backported security fixes.

## Security invariants for contributors

These rules come from [Principles](/architecture/principles), which outranks every other project document. A change that breaks one is not a style issue. It needs an amendment to the principles, proposed and agreed in its own pull request, before any code relies on it.

### The daemon listens on loopback only

The HTTP API binds `127.0.0.1` and nothing else. Every router that reads or changes vault state declares the `require_token` dependency, so its requests must carry the API token in `X-Coffer-Token`. Only the readiness probe, `GET /api/v1/daemon/status`, answers without it. The token is minted on each daemon start and published in `~/.coffer/daemon.json`, written with mode `0600`. A host guard also rejects any request whose `Host` header is not a loopback authority (`127.0.0.1`, `localhost`, `::1`). That check defeats DNS rebinding, where a web page re-resolves its own hostname to `127.0.0.1`.

When you contribute:

- Never add a bind address, flag or setting that exposes the daemon beyond loopback.
- Give every new router `dependencies=[Depends(require_token)]`, and never exempt a route from the host guard.
- CORS is not the security boundary, and widening it grants nothing. The token is the boundary. Do not treat an origin check as authentication.

### Secrets exist only as ciphertext

Secrets live only as Fernet ciphertext in the `credentials` table. Plaintext exists in memory only between decryption and the spawn or header injection that consumes it.

- Store a **credential reference**, never a secret, in any other table, config file, resource spec or API response.
- Never let plaintext reach the database, a log line, the audit log or any structured event. Watch exception messages and `repr`s that might include a request header or an environment block.
- The Fernet master key is managed only by `coffer.infrastructure.credentials`. By default it is a `0600` file beside the database, or it lives in the OS keychain when the user opts in. It never goes into anything the vault publishes, such as a sync remote. It reaches another machine only through the explicit key export and import.
- Credential material leaves the machine only as ciphertext, and only when the user explicitly asks.

The `secrets-scan` CI job runs gitleaks over the full git history. A committed secret fails the pull request even if a later commit removes it. Use obviously fake values in tests and fixtures.

### `keyring` stays confined

Only `backend/coffer/infrastructure/credentials/keyring_adapter.py` imports `keyring`. Every other module passes credential references. Import-linter contracts in `backend/pyproject.toml` enforce this ("keyring confined to infrastructure", "CLI does not access the keychain directly"), and `make lint` runs them. Do not add an `ignore_imports` waiver to get around them. Route the need through the credentials module instead.

### Outbound requests to user-supplied URLs go through the SSRF guard

`coffer.infrastructure.net.ssrf_guard.check_url` resolves a URL's host and rejects loopback, private, link-local and carrier-grade NAT destinations. The probes the provider editor runs before anything is saved (list models, test connection, detect protocol) validate the base URL with it. Endpoints the user configures as their own — HTTP MCP upstreams, model and transcription calls, the IM platforms, the sync remote — are exempt once Coffer is using them, because a loopback or LAN endpoint is a legitimate target there ([Principles → Network defaults](/architecture/principles)). When you add code that makes the daemon fetch a URL a user supplied, validate it with `check_url` first. The guard does not pin the resolved address through to the HTTP client, so a DNS-rebinding host could pass validation and then resolve elsewhere. That residual risk is accepted for a single-user, loopback-only daemon whose URLs come from its own user.

### User content stays on the machine

All vault state lives on the user's machines. Cloud services act only as model and tool providers, never as the system of record. The single exception is vault sync to a git remote the user owns: off by default, with secrets only as ciphertext, and the remote treated as a meeting point that can be rebuilt from any one machine. A feature that sends vault content to any other remote service needs a principles amendment.

### Paths from users and agents are guarded

Knowledge paths go through one traversal guard, `infrastructure/knowledge/paths.py`, that refuses empty, all-dot, hidden or otherwise unsafe path segments. When you add an endpoint that turns a user- or agent-supplied string into a filesystem path, route it through the owning module's guard rather than joining paths yourself.

## Checklist for a security-relevant change

- [ ] No new listener, bind address or route that bypasses the token and host checks.
- [ ] No secret in a table other than `credentials`, in a log, in the audit log or in an API response.
- [ ] No new `keyring` import outside the credentials module, and no new import-linter waiver.
- [ ] User-supplied outbound URLs are validated with the SSRF guard.
- [ ] User- or agent-supplied paths go through a traversal guard.
- [ ] Tests use fake secrets, and `make verify` is green, including `lint-imports`.
- [ ] The pull request description names the principle the change touches and explains why the change respects it.

## Related

- [Security model](/architecture/security)
- [Credentials guide](/guides/credentials)
- [Design principles](/architecture/design-principles)
- [`SECURITY.md`](https://github.com/wyx-sg/Coffer/blob/main/SECURITY.md)
