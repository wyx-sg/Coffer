## Why

Rewriting the documentation site from the code up found places where the
specs and the code disagree. Some are code that falls short of a promise the
spec rightly makes; others are specs that describe a behaviour the code never
had and should not have. This change settles each one, so the specs on `main`
describe the code on `main`.

## What Changes

- `GET /api/v1/daemon/status` reports `ready` or `draining`: the port opens
  only after startup, so no request ever sees a starting daemon, and a client
  that spawned one waits a bounded time for the probe.
- `coffer daemon status` only looks: with no daemon it says "not running" and
  exits non-zero instead of starting one.
- Claude Code's `apiKeyHelper` runs the coffer CLI by absolute path, so it works
  whatever `PATH` Claude Code runs with; de-projection recognises both that form
  and the bare one earlier builds wrote. The projection target is the agent's
  own `<config_dir>/settings.json`.
- Claude Code's `agents/` directory entry is named by its real key, `subagents`.
- Memory files a `feedback` entry into its project's partition when it carries a
  project root; only `user` entries always go to `global`. Distil runs on its own
  upkeep interval over partitions with new raw entries, not after each
  aggregation.
- The engine settings page is named as the UI names it: Settings → Coffer's
  model.
- A group reply is attached through the platform's reply primitive where it has
  one; on SeaTalk the thread rooted at the triggering message is the attachment.
  The channel page and CLI edit the group-gating switches `require_mention` and
  `ignore_other_mentions`.
- Pasting an HTTP MCP server's `headers` object reviews its values for secrets
  like `env`.
- The sync interval has a 60-second floor on every surface; `coffer sync remote
  pause` / `resume` switch a remote off and on; the round steps name the
  publish-side deletion guard at step 1 and the apply-side one at step 4.

## Capabilities

### New Capabilities

### Modified Capabilities

- `daemon`
- `provider-switching`
- `agent-registry/claude-code`
- `memory`
- `internal-engine`
- `channels`
- `web-ui`
- `vault-sync`

## Impact

The daemon status probe schema and `coffer daemon status`; the Claude Code
provider projection; memory filing and the distil worker; the SeaTalk adapter's
group reply; the channel edit dialog and CLI; the MCP JSON import dialog; the
sync remote schema and `coffer sync remote`; acceptance markers and citations
that quote the renamed internal-engine requirement; the docs-site pages that
recorded these as gaps.
