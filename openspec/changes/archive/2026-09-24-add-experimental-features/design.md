## Context

Everything lands on `main`, and `release.yml` builds a tagged `main`. There is
no build channel and no feature switch: the 30 routers are one unconditional
table (`surfaces/http/routing.py`), the workers start unconditionally
(`surfaces/http/background_workers.py`), and the CLI groups are one list
(`surfaces/cli/main.py`). The only on/off controls are the internal-engine
upkeep switches, which live in the synced database, and each resource's
`enabled`. The reasoning behind gating instead of branching is recorded in
[Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md).

## Goals

- A tagged release exposes only stable features; a local build exposes all.
- The owner tests everything from `main`, in the installed app, with no second
  branch.
- A switched-off feature is invisible on every surface and keeps its data.

## Decisions

### The channel is a constant stamped at build time

`coffer/build_channel.py` holds `CHANNEL = "dev"` in the repository.
`scripts/stamp_channel.py stable` rewrites it in the release workflow before
PyInstaller runs, so only a tagged release is `stable`. `sys.frozen` is not the
signal, because the owner's own testing build is frozen too. The frontend and
the desktop shell never stamp anything; they read the channel from
`GET /api/v1/daemon/status`.

### A feature's state has three layers, resolved per read

1. `COFFER_FEATURES` (`vault_sync=on,memory=off`), read once at start. A pinned
   feature cannot be changed at runtime; a write answers 409 `FEATURE_PINNED`.
2. The `features` object in `~/.coffer/daemon-config.json`, written through the
   existing merge helper. It is machine-local on purpose: the database syncs, and
   a switch in it would switch every machine at once.
3. The channel default: `stable` → off, `dev` → on.

`FeatureService` (application layer) holds the resolved state, answers
`is_enabled(key)`, and notifies subscribers on change. Domain holds the
registry: key, and which surfaces the key owns.

### Gate at request time, not at wiring time

Switching takes effect without a restart. A restart-to-apply switch would need
a restart control in the web UI, which spec web-ui "Leave daemon controls to the
CLI" rules out, and the upkeep workers already read their switches on every
round.

- **REST**: routers for the three features are included with a dependency that
  raises 404 `FEATURE_DISABLED` naming the key. Routes stay registered, so the
  OpenAPI document and the generated client do not change with the switch.
- **MCP**: the builtin-tool registry records which feature owns a tool.
  `tools/list` omits tools whose feature is off, and a call to one answers
  exactly as a call to an unknown tool does.
- **Workers**: converge, curation, aggregation and distil check the feature at
  the top of each round and skip it. The sync object is still constructed,
  because curation takes its lock.
- **CLI**: the groups stay registered. The shared error path turns
  `FEATURE_DISABLED` into one line naming `coffer daemon features enable <key>`,
  exiting 1.
- **Web**: the status response carries `features`. The sidebar filters on it;
  a gated route renders an empty state that links to Settings → General.
- **Desktop**: the shell already reads the status. With `vault_sync` off the
  tray has no Sync item and the sync watcher does not poll.

### Side effects bound to a switch

- `memory` off → the delivery reconcile removes the memory hook from every
  agent; on → the same reconcile installs it. This reuses the boot heal.
- `knowledge` off → the `coffer-guide` catalogue is rewritten without the
  knowledge section, the channel `/save` answers with a notice, and
  `coffer__write` leaves the tool list.
- `vault_sync` off → no round runs, and nothing raises sync attention.

The kinds stay registered. A switched-off feature's resources, files, remote
configuration and history are untouched.

## Risks / Trade-offs

- Request-time gating costs one dictionary lookup per gated request, which is
  negligible.
- A route of a switched-off feature still appears in `/openapi.json`. The
  contract is stable and the switch is runtime state.
- An agent session that listed tools before a switch keeps a stale list until
  it lists again. The call answers as an unknown tool.
