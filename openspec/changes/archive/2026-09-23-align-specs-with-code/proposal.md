## Why

An audit of every capability spec against the code found requirement text, data
models and wire contracts that describe behaviour the code deliberately left
behind — renames to uid addressing, removed fields, retired passes, statuses and
error codes added later — plus shipped, user-visible behaviour no requirement
covers. The gates check that scenarios have tests and that contract field names
match; they cannot see a requirement sentence, a status code, an enum value or a
field's type that has drifted. This change makes the specs say what the code on
`main` does, and specifies the shipped behaviour that had no requirement.

## What Changes

- Rewrite requirement text and scenarios whose wording contradicts deliberate code
  behaviour, each backed by an ADR, a code comment, a later change or a test.
- Add requirements, each with an acceptance-tested scenario, for shipped behaviour
  that had none: channel edit, test delivery and delete on the Channels page; the
  conversation-list title search; daemon residency over REST, the CLI and
  Settings; the curation owner's route, command and Settings row; folding repeated
  failed and held sync rounds.
- Correct each capability's `data-model.md` where entities, fields, service
  methods, enums or migrations differ from the code.
- Correct each `contracts/api.openapi.yaml` where status codes, error codes, enum
  values, `required` lists or descriptions differ from what the routes serve, and
  regenerate the frontend client.
- Correct `## Purpose` sections that state a gap the code has since closed.

## Capabilities

### New Capabilities

### Modified Capabilities

- `agent-registry`, `agent-registry/claude-code`, `agent-registry/codex`
- `channels`, `channels/telegram`, `channels/seatalk`
- `chat`
- `credentials`
- `daemon`
- `desktop-app`
- `internal-engine`
- `knowledge`
- `mcp-gateway`
- `memory`
- `provider-switching`
- `resource-framework`
- `skill-manager`
- `vault-sync`
- `web-ui`

## Impact

Specs, data models and contracts under `openspec/specs/`, the regenerated clients
under `frontend/src/lib/api/generated/`, and new acceptance-marked tests. No
runtime code changes behaviour.
