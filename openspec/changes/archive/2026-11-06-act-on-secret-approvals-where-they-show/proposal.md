## Why

A review of secret management on 2026-11-06 (owner approved the list) found places where a
secret held for approval left the person without a next step, a misleading error, a copied
value that lingers on the pasteboard, and two leftovers in the CLI that nobody needs.

## What Changes

- An MCP server's Requires block: a secret waiting for approval offers Open approvals; a
  refused one offers Ask again (Touch ID in the desktop app).
- A model provider whose key is held for approval reads Waiting for approval or Refused, with
  the matching button, instead of Unreachable and an agent hand-off.
- `SECRET_BINDING_REJECTED` no longer points at the Secrets page; it says to press Ask again
  where the secret is used.
- Copying a revealed value goes through the shell: concealed and transient markers, cleared
  after 90 seconds unless something else was copied (ADR
  `a-copied-secret-is-marked-concealed-and-cleared-after-90-seconds`).
- `coffer run --secret` requires `ENV=`; the variable name derived from the id is gone.
- `coffer secret key-install` is removed; installing a key goes through the desktop app only.

## Impact

- Specs secret, mcp-gateway, provider-switching (edited in place, so scenarios could be
  renamed).
- Frontend MCP and provider pages, reveal dialogs; desktop `clipboard.rs`; CLI `run`,
  `secret`; docs-site guides and CLI reference (English and Chinese); coffer-guide skill.
