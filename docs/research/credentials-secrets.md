# Competitive Research — Credential & Secret Management for Agents & MCP

> English: this file · 中文版: [credentials-secrets.zh.md](./credentials-secrets.zh.md)
>
> Internal competitive-research report for Coffer's credential store (constitution
> Principle; ADR-015). **Date:** 2026-06-16. **Method:** deep-research harness.
> **Provenance caveat:** this run hit an API session limit during verification, so
> claims could not be re-verified by vote — but they are drawn from primary
> vendor docs (1Password, ToolHive, Infisical, Vault) and reflect well-documented
> behaviour. Flag for a light fact-check before external quoting.

## 1. Landscape at a glance

Secret management for agents/MCP spans four postures:

| Posture                   | Where secrets live          | How config refers to them | Examples                         |
| ------------------------- | --------------------------- | ------------------------- | -------------------------------- |
| **Local encrypted store** | encrypted file + OS keyring | injected at spawn         | ToolHive (Encrypted), **Coffer** |
| **Hosted secret manager** | vendor vault                | `op://` / `${ref}` URIs   | 1Password, Infisical, Doppler    |
| **Enterprise vault**      | server (dynamic)            | API / agent injection     | HashiCorp Vault                  |
| **Encrypted-in-config**   | the git repo itself         | inline ciphertext         | SOPS+age, git-crypt              |

### The players

- **1Password** — the reference design for "access without exposure." Secrets are
  referenced by **`op://<vault>/<item>/[section/]<field>`** URIs, never inline.
  **`op run`** scans env for `op://` refs, resolves them, and runs the command in
  a subprocess with the values as env vars that vanish on exit
  (materialize-at-spawn). `.mcp.json` uses `${VAR}` placeholders so config is
  safe to version-control. 1Password's stated policy is **not to expose raw
  credentials through MCP**; in the 1Password + Runlayer integration the secret
  stays in the vault while the MCP control plane stores **only a reference**, and
  injection is via **HTTP header injection** (resolve `op://` in transport
  headers, plaintext in memory only for the request). [1password.com/blog;
  developer.1password.com]
- **ToolHive** — three secret providers (**Encrypted** local default, **1Password**
  read-only, **Environment** read-only), one active at a time. The Encrypted
  provider stores ciphertext locally and **derives its key from a password kept
  in the OS keyring** (Keychain / Credential Manager / dbus). Injection is
  `thv run --secret <name>,target=<ENV_VAR>`. [docs.stacklok.com/toolhive]
- **Infisical** — OSS (MIT) self-hostable secret manager; secret references via
  interpolation (`${KEY}`, `${dev.KEY}`, `${prod.frontend.KEY}`); ships an MCP
  server. [infisical.com/docs]
- **HashiCorp Vault** — BSL source-available; **dynamic, short-lived credentials**
  (e.g. ephemeral database creds) — the rotation gold standard.
- **SOPS + age / git-crypt** — encrypt secret _values inside config files_ that
  live in the repo (keys plaintext, values ciphertext); the encryption key is
  bootstrapped out-of-band.
- **mcp-auth-proxy** — a drop-in OAuth 2.1/OIDC gateway in front of an MCP server;
  delegates identity to Google/GitHub/Okta/Auth0/Azure AD/Keycloak rather than
  storing credentials, with an optional shared-password fallback.
  [github.com/sigbit/mcp-auth-proxy]

## 2. Capability comparison

| Capability                  | 1Password          | ToolHive        | Infisical      | Vault          | **Coffer**                         |
| --------------------------- | ------------------ | --------------- | -------------- | -------------- | ---------------------------------- |
| Secrets at rest             | vault (cloud/self) | encrypted local | vault          | server         | **Fernet ciphertext, local table** |
| Refs in config (not values) | ✅ `op://`         | ✅ name         | ✅ `${}`       | ✅ path        | **✅ credential refs**             |
| Inline-secret rejection     | (convention)       | —               | —              | —              | **✅ pattern-rejects inline**      |
| Materialize at spawn        | ✅ `op run`        | ✅ `--secret`   | ✅             | ✅             | **✅ at upstream spawn**           |
| Header injection (HTTP)     | ✅ Runlayer        | —               | —              | —              | **✅ for http transports**         |
| Master-unlock model         | account            | OS keyring pw   | account        | unseal         | **0600 file / OS keyring opt-in**  |
| Rotation / dynamic secrets  | rotation           | —               | **✅ dynamic** | **✅ dynamic** | **❌ static**                      |
| External-provider refs      | n/a (is one)       | ✅ 1Password    | n/a            | n/a            | **❌ own store only**              |
| Sharing / teams             | ✅                 | partial         | ✅             | ✅             | **❌ single user**                 |
| Local-first / self-host     | partial            | ✅              | ✅             | ✅             | **✅ strict**                      |
| Sole-owner isolation        | —                  | —               | —              | —              | **✅ daemon-only access**          |

## 3. How Coffer compares

**Where Coffer is at parity with — or stronger than — best practice.**

1. **Coffer already implements 1Password's "access without exposure" ideal.**
   Refs-in-config (never values), materialize-only-at-spawn, header injection for
   HTTP transports, and ciphertext-only in audit/logs/sync is _exactly_ the model
   1Password advocates (and that ToolHive implements). Coffer is on the right side
   of the industry security thesis.
2. **Inline-secret rejection is a genuine plus.** Coffer actively rejects
   secret-looking inline values in MCP config and forces them into refs — most
   tools rely on convention; Coffer enforces it.
3. **Daemon-sole-owner is stronger isolation than most.** A single writer, all
   surfaces reaching secrets only through the daemon API, beats the typical
   "any CLI process can read the store" model.
4. **Local-first encrypted store + OS-keyring-protected master key** mirrors
   ToolHive's Encrypted provider — parity with the best local design.

**Where Coffer lags — concrete borrows.**

1. **No external-provider refs (the biggest borrow).** 1Password (`op://`),
   ToolHive (1Password provider), and Infisical let config point _into_ an
   existing vault. Coffer only stores secrets in its own table. Add a
   provider-ref scheme so a Coffer credential ref can resolve from 1Password /
   Infisical / Vault — users who already run a vault should not duplicate secrets
   into Coffer.
2. **No rotation / TTL.** Vault issues dynamic short-lived creds; Coffer's are
   static. Add rotation hooks / expiry, at least re-prompt-on-expiry.
3. **No sharing / teams / dynamic secrets** — deliberate single-user scope; note
   it consciously.

## 4. Key takeaways for Coffer

1. **You already implement the industry's "access without exposure" ideal** —
   refs + materialize-at-spawn + ciphertext-everywhere + inline-secret rejection.
   Lead with that; it is a strength, not a gap.
2. **Biggest borrow: external-provider credential refs** (`op://`-style) so a
   Coffer ref can resolve from 1Password / Infisical / Vault instead of forcing a
   second copy of the secret into Coffer's store.
3. **Add rotation / TTL hooks** (Vault-inspired) for credentials that expire.
4. **Keep daemon-sole-owner + inline-secret rejection** — both are stronger than
   the field's norm.

## 5. Sources

Primary:

- developer.1password.com/docs/cli/secret-references · /docs/cli (op run)
- 1password.com/blog — securing-mcp-servers-with-1password, where-mcp-fits-and-where-it-doesnt, secure-mcp-credentials-1password-runlayer
- docs.stacklok.com/toolhive/guides-cli/secrets-management
- infisical.com/docs/documentation/platform/secret-reference
- developer.hashicorp.com (Vault dynamic secrets) · getsops.io · github.com/AGWA/git-crypt
- github.com/sigbit/mcp-auth-proxy
