# Experimental features

Coffer is developed on one line: every capability lands on `main`, and a release is a tagged `main`. Some capabilities are still being reshaped, so rather than hold them back on a separate branch, Coffer ships them **switched off by default** in a release and lets you switch each one on, on your own machine, whenever you like.

## Release channels

Every build carries one **release channel**:

| Channel | Which builds | Experimental features start |
| --- | --- | --- |
| `stable` | A tagged release — the `.dmg` and the CLI archive from GitHub Releases, and the one-line installer | **off** |
| `dev` | Everything else — a source install, `make desktop`, any build you made yourself | **on** |

The channel is fixed when the build is made; nothing at runtime changes it. `coffer daemon status` prints it, and so does `coffer daemon features list`.

## Which features are experimental

| Key | What it switches | Guide |
| --- | --- | --- |
| `vault_sync` | Converging the vault with a git remote you own | [Sync](/guide/sync) |
| `knowledge` | The knowledge layer: collections, curation, `coffer__write` | [Knowledge](/guide/knowledge) |
| `memory` | Reading, distilling and delivering the agents' memory | [Memory](/guide/memory) |

Everything else in Coffer is always on.

## Switch a feature on or off

From the web UI or the desktop app: **Settings → General → Experimental features**, one switch per feature.

From the command line:

```bash
coffer daemon features list
```

```
channel: stable
vault_sync   off  (channel default)
knowledge    on   (set on this machine)
memory       off  (channel default)
```

```bash
coffer daemon features enable knowledge
coffer daemon features disable knowledge
```

The last column says what decided each state: the channel default, a choice made on this machine, or a pin (below).

**A switch takes effect at once.** There is no restart: the running daemon opens or closes the feature's pages, commands, tools and background passes the moment you switch it. An agent session that listed Coffer's tools before the switch sees the new list the next time it lists them.

**A switch belongs to one machine.** It is kept in `~/.coffer/daemon-config.json`, next to the daemon's port, and it never syncs — switching memory on on your laptop leaves your desktop as it was.

## What "off" means

While a feature is off, Coffer behaves as if it were not there:

- its entry leaves the sidebar, and opening one of its pages directly shows a notice linking to Settings → General;
- its commands (`coffer sync`, `coffer knowledge`, `coffer memory`) print one line telling you to run `coffer daemon features enable <key>`, and exit 1;
- its REST routes answer 404 with the code `FEATURE_DISABLED`;
- its MCP tools leave the tool list your agents see;
- its background passes skip their rounds; with sync off the tray has no Sync item.

Switching `memory` off also takes Coffer's memory hook out of every agent it manages, and switching it on puts the hook back. Switching `knowledge` off drops the knowledge catalogue from the `coffer-guide` skill your agents load.

**Switching off deletes nothing.** Collections, notes, memory files, the sync remote and its history all stay exactly where they are, and switching the feature back on picks up where it stopped. Database migrations run whatever the switches say, so switching a feature on never needs an upgrade step.

## Pinning a feature (tests and CI)

`COFFER_FEATURES` pins features for the lifetime of one daemon process, above both the machine setting and the channel default:

```bash
COFFER_FEATURES=vault_sync=on,memory=off coffer daemon start
```

A pinned feature cannot be switched while that daemon runs: the settings switch and `coffer daemon features enable|disable` are refused with `FEATURE_PINNED`. An unknown key, or an entry that is not `key=on|off`, is logged and ignored.
