## MODIFIED Requirements

### Requirement: Present a Sync page with Status, Machines and Remote tabs
The web UI MUST present a top-level **Sync** page. The header says in one status whether this machine
is in sync: In sync, N changes to push, N changes pulled, Syncing, Stopped (conflicts or deletions
held), Push failed, Not pushed: plaintext secret, Remote unreachable, Sign-in failed, Paused or Not
set up. Beside the status is the page's one round action, **Sync now** (Syncing… and disabled while a
round runs), which never changes with the state; under the title is the remote's URL with a copy
button, the branch and when rounds run. The title carries the Experimental mark. The page has **three** tabs:

- **Status** is the landing tab. It holds:
  - a banner saying what the status means now, with one grey line under it of what the vault holds
    that syncs: knowledge documents, skills, MCP server and tool definitions, and whether secrets
    are synced;
  - what waits to push, five lines then "Show all";
  - a card for a round stopped on conflicts or held deletions, and for a join's differing files;
  - the problem a failed round met, as a card with its own action and an × that ignores it like
    Ignore on Overview. A card has no Retry; the vault inside a cloud-synced folder is moved with
    "Move the vault…";
  - every round this machine has run, as a table of when, the round, what it pulled and pushed. A
    round opens in a drawer with its snapshot, the commits it pulled, what it changed here and what
    it pushed, and Roll back to before the round is there and nowhere else.
- **Machines** lists the machine registry. A user renames this machine and retires one that is
  gone, at once, with Undo.
- **Remote** holds the remote's settings, each saved as it is changed:
  - the URL, the branch and the push secret;
  - when a round runs. "Only when I press Sync now" pauses the remote;
  - whether secret ciphertext travels, which asks first when switched on;
  - the vault's folder, with a warning when it sits in a synchronised folder;
  - Stop syncing, which runs at once and offers Undo.

Resolving conflicts and reviewing held deletions each have their own view, `/sync/conflicts` and
`/sync/deletions`, reached from the Status card and returning to it. Until this machine has joined
a remote, the page shows setting one up and joining in place of the tabs. The master key is
imported and exported in Settings › Security, not on the Sync page.

#### Scenario: the Sync page opens on Status beside Machines and Remote
- **GIVEN** the web UI with a joined remote
- **WHEN** the user opens the Sync page
- **THEN** it has exactly three tabs, Status, Machines and Remote, and opens on Status
- **AND** a link to a tab that no longer exists lands on Status

### Requirement: Converge shared state areas
Module-owned shared state that belongs to the vault rather than to one machine
MUST converge as vault state documents under `vault/state/<area>/`: MCP
capability switches (`state/mcp-preferences/<server>.json`), channel peer
pairings (`state/channel-peers/<channel>.json`) and Coffer's own settings — the
model timeout, the speech-to-text model and the upkeep switches
(`state/settings/internal-engine.json`). A state document names its owner by
uid; an area with nothing but its defaults has no document. The plugin
inventory is not a state area: it is carried in each machine's descriptor (see
"Record plugins as an inventory, not a replicator").

#### Scenario: each shared state area reaches the working tree
- **GIVEN** a switched-off MCP capability, a channel pairing and a non-default Coffer setting
- **WHEN** each is stored
- **THEN** each is a vault document under its area, named by its owner, and when each capability was first and last seen stays in `derived/`
- **AND** Coffer settings at their defaults have no document

### Requirement: Keep machine identity across reinstalls
`machine_id` MUST survive reinstalling and uninstalling Coffer. A machine that
comes back under a new identity becomes a ghost: it rejoins as a stranger, its
old descriptor lingers in the registry with nobody to update it, and anything
that named it — a channel's binding — silently stops meaning
this machine.

#### Scenario: a machine identity survives reinstalling Coffer
- **GIVEN** a machine whose cached identity is lost, on a host that exposes a stable identifier
- **WHEN** its identity is resolved again and it joins the remote
- **THEN** it has the same machine id, the remote's registry holds it, and it joins as a returning machine rather than as a stranger

### Requirement: Move the vault out of a synchronised folder
A vault found inside a folder another tool synchronises (the "Cloud folder" problem) MUST be movable
from the Sync page. `POST /api/v1/sync/vault/move` takes `{to}` and answers `{from, to}`. The vault's
path is fixed (`~/.coffer/vault`), so a vault elsewhere is reached through that path and a move never
changes a path any part of the daemon holds: when `to` is `~/.coffer/vault` itself a real folder
replaces the link, otherwise the folder is placed at `to` and `~/.coffer/vault` becomes a link to it.
No restart is needed. The target MUST be absolute (`~` allowed), absent or empty, outside and not
around the current vault, in a writable parent, and not inside a folder the Cloud folder detector
names: `SYNC_VAULT_TARGET_INVALID` (422), `SYNC_VAULT_TARGET_IN_CLOUD` (422) and
`SYNC_VAULT_TARGET_NOT_EMPTY` (409). While it moves, rounds and agent writes are
held off by the sync lock; the folder is renamed, or copied and then emptied when the target is on
another filesystem; the git repository (HEAD, working-tree status, connectivity) is checked at the
new place against the old; any failure puts the vault back and is `SYNC_VAULT_MOVE_FAILED` (500).
The old folder is left empty for the person to delete. `GET /api/v1/sync/status` carries
`vault_real_path` (where the files really are, the dialog's "From") and `default_vault_path` (the
"To" it offers).

#### Scenario: the vault is moved out of a synchronised folder
- **GIVEN** a git vault in iCloud Drive that `~/.coffer/vault` links to, and the Cloud folder problem showing
- **WHEN** the vault is moved to `~/.coffer/vault`
- **THEN** the response is `{from, to}` with the iCloud folder and the new folder, the vault's files and history are at the new place unchanged, and the old folder exists empty
- **AND** the status no longer reports a synchroniser or a problem, and rounds and writes go on at the same path
- **AND** a target inside iCloud Drive, a cloud drive or a Syncthing folder is `SYNC_VAULT_TARGET_IN_CLOUD`, a relative or overlapping path is `SYNC_VAULT_TARGET_INVALID`, and a folder with files in it is `SYNC_VAULT_TARGET_NOT_EMPTY`, each leaving the vault where it was

## REMOVED Requirements

### Requirement: Run an unattended rewriter on one owner machine
**Reason**: The knowledge layer no longer runs a model that rewrites synced documents on a timer, so no unattended rewriter exists to name an owner for. Mechanical passes (the knowledge sweep, aggregate, distil) write only what they derive from a single machine's own input and go through the vault writer like any other write.
**Migration**: None. The curation owner setting is ignored on read and dropped on the next write of the settings document.

### Requirement: Report and change the rewriter's owner
**Reason**: There is no owner machine to report or change.
**Migration**: None.

### Requirement: Never overlap a curation pass and a round
**Reason**: There is no curation pass. The knowledge sweep writes through the vault writer under the same lock as every other write and holds nothing against a round.
**Migration**: None.
