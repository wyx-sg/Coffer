## Why

A channel was a synced vault resource that named, in `runs_on`, the one
machine allowed to run it. Everything else in its file was machine-specific
too: `default_agent` is the uid of an agent that exists only on one machine,
`directories` are local paths, and which agents it may drive lives in the
machine-local reach record. Every comparable product (OpenClaw, cc-connect,
Claude Code Channels, Codex Remote / Remote Control) keeps a bot connection on
one machine, because the platforms allow one consumer per bot. See
[Channels Are Machine-Local Resources](../../../docs/decisions/channels-are-machine-local-resources.md).

## What Changes

- **BREAKING** A channel is a machine-local resource like an agent: its file is
  under `local/resources/channel/`, its pairings in `local/channel-peers.json`;
  neither is committed or synced.
- **BREAKING** `runs_on` is removed from the channel configuration, and
  `runs_on` / `runs_here` from the channel status. The Channels page loses the
  Runs on setting, the Elsewhere group, the unbound / unknown-machine states and
  Run it here.
- A one-time startup migration moves each machine's own channels (and their
  pairings) out of the vault and deletes the vault copies in one commit. It is
  deleted once every machine has run it.

## Impact

- Specs: `channels`, `vault-sync`.
- Code: channel kind (storage class), runtime gate, channel status and routes,
  pairing store, vault state rules, the Channels page.
- Docs: vault sync, resource framework, chat architecture, channel guides, ADRs.
