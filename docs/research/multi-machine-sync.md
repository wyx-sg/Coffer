# Multi-machine sync: how other products do it

**Feature**: converging one user's config and knowledge vault across their own machines through a user-owned remote (git), with bidirectional apply, deletion safety, new-machine join, per-machine differences and encrypted secrets · **Coffer spec**: [vault-sync](../../openspec/specs/vault-sync/spec.md) · **Related ADRs**: [vault-sync](../decisions/vault-sync.md), [sync-deletion-breaker](../decisions/sync-deletion-breaker.md), [sync-machine-identity](../decisions/sync-machine-identity.md), [single-owner-machine-for-unattended-rewrites](../decisions/single-owner-machine-for-unattended-rewrites.md), [credentials-across-machines](../decisions/credentials-across-machines.md), [sync-withholds-derived-output](../decisions/sync-withholds-derived-output.md), [resource-reach-is-machine-local](../decisions/resource-reach-is-machine-local.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (official docs, repo source files, release notes); stars and release dates checked 2026-09-24 via the GitHub API

## Scope and selection

The survey covers five questions every multi-machine sync tool has to answer:

1. **Merge semantics**: what happens when two machines changed the same thing.
2. **Deletions**: how a delete is represented, propagated, and stopped when it is a mistake.
3. **First join**: what happens when a machine that already has local state connects to an existing remote.
4. **Per-machine differences**: how one shared state produces different results on different machines.
5. **Secrets**: how credentials travel through storage the user does not fully trust.

Products, by adoption as of 2026-09:

| Product | Class | Stars / reach | Latest release |
| --- | --- | --- | --- |
| cc-switch | AI-agent config switcher with WebDAV/S3 sync | 136k | v3.20.4, 2026-09-22 |
| Syncthing | P2P file sync | 88.9k | v2.1.5, 2026-09-08 |
| Logseq | Notes app with sync | 45.0k | (continuous) |
| mise | Tool/env manager | 34.2k | (not surveyed further, see below) |
| Atuin | Shell history with encrypted sync server | 31.8k | v18.23.0, 2026-09-22 |
| age / SOPS | Encryption for files in repos | 23.7k / 23.2k | SOPS v3.13.3, 2026-07-23 |
| chezmoi | Dotfile manager over git | 21.7k | v2.72.2, 2026-09-13 |
| obsidian-git | Obsidian plugin, vault over git | 12.0k | 2.40.0, 2026-09-17 |
| git-crypt | Transparent encryption in git | 9.9k | 0.8.0, 2025-09-23 |
| yadm | Dotfile manager, bare-git wrapper | 6.4k | (last push 2026-04) |
| rulesync | AI rule generator | 1.5k | v18.0.0, 2026-09-24 |
| AIS (ai-rules-sync) | AI rule linker | 38 | — |
| VS Code Settings Sync, JetBrains Backup and Sync, Obsidian Sync, Dropbox, OneDrive | Vendor-cloud sync | built into products with tens of millions of users | — |

mise, dotbot and GNU Stow were considered and dropped from the detailed survey: they install or link files from a repo but have no merge, deletion, encryption or join semantics of their own; git does all of it.

---

## Git-transport dotfile managers

### chezmoi

**Model.** Three states ([concepts](https://www.chezmoi.io/reference/concepts/)): the *source state* (a git working tree, default `~/.local/share/chezmoi`, identical on every machine), the machine-local *config file* (`~/.config/chezmoi/chezmoi.toml|yaml|json`), and the *destination state* (the real home directory). The *target state* is computed from source + config + destination, then applied. The repo is transport and history; each machine renders its own result.

**Merge semantics.** chezmoi does not merge. `chezmoi update` runs `git pull --autostash --rebase` in the source directory and then `chezmoi apply` ([update](https://www.chezmoi.io/reference/commands/update/)), so text conflicts surface as ordinary git rebase conflicts in the source repo. Between source and destination it detects drift: it records what it last wrote in a persistent state file (`chezmoistate.boltdb`, next to the config, [global flags](https://www.chezmoi.io/reference/command-line-flags/global/)), and "if a target has been modified since chezmoi last wrote it then the user will be prompted if they want to overwrite the file" ([apply](https://www.chezmoi.io/reference/commands/apply/)). `chezmoi merge` opens a three-way merge tool across source, target and destination; `chezmoi re-add` pulls destination edits back into source (not for templates) ([usage FAQ](https://www.chezmoi.io/user-guide/frequently-asked-questions/usage/)). Nothing records a change until an explicit command runs, which is why the FAQ says chezmoi is unsuitable for rapidly changing files like shell history and points to Atuin.

**Push.** Optional `git.autoCommit` / `git.autoPush` commit and push every source change with a generated message, with the warning that a plaintext secret added by mistake is pushed too ([daily operations](https://www.chezmoi.io/user-guide/daily-operations/)).

**Deletions.** A file missing from source is *not* removed from machines; deletion is explicit. Options ([target types](https://www.chezmoi.io/reference/target-types/)): a `remove_` prefixed entry removes the target; an `exact_` directory removes anything in the target not in source; `.chezmoiremove` is a (templated) list of targets to remove ([chezmoiremove](https://www.chezmoi.io/reference/special-files/chezmoiremove/)). An empty file is deleted unless marked `empty_`. So the tombstone is a file in the repo, and the default is "never delete what you were not told to".

**First join.** `chezmoi init <repo>` clones, `chezmoi diff` previews, `chezmoi apply` writes; `init --apply` does both ([setup](https://www.chezmoi.io/user-guide/setup/)). If the repo contains `.chezmoi.<format>.tmpl`, `init` renders it into the machine's config; `promptStringOnce` asks for a value only if it is not already in the local data. This is the join-time questionnaire that seeds per-machine data.

**Per-machine differences.** Files that vary are Go `text/template`s using built-ins (`.chezmoi.hostname`, `.chezmoi.os`, ...) and the machine's `[data]` section; `.chezmoiignore` is itself a template, so whole files can be skipped per host ([machine-to-machine differences](https://www.chezmoi.io/user-guide/manage-machine-to-machine-differences/)). `create_` writes a file only if absent (seed once, then machine-owned); `modify_` is a script that receives the current file on stdin and emits the new one, for files that are partly managed ([target types](https://www.chezmoi.io/reference/target-types/)).

**Secrets.** Four whole-file backends: age, git-crypt, gpg, transcrypt. Encrypted files live ASCII-armored in source with the `encrypted_` attribute; `chezmoi edit` decrypts and re-encrypts transparently ([encryption](https://www.chezmoi.io/user-guide/encryption/)). With age, the config names `identity` and `recipient`(s); a builtin age is used if the binary is missing, but it refuses passphrases because chezmoi decrypts on every `diff`/`status`, not only on `apply` ([age](https://www.chezmoi.io/user-guide/encryption/age/)). The documented bootstrap for a new machine: commit `key.txt.age` (the age private key, passphrase-encrypted, ignored as a target) plus a `run_onchange_before_` script that decrypts it to `~/.config/chezmoi/key.txt` once; the user types the passphrase only at `chezmoi init --apply` ([encryption FAQ](https://www.chezmoi.io/user-guide/frequently-asked-questions/encryption/)). Password-manager template functions (1Password, Bitwarden, pass, ...) keep secrets out of the repo altogether and resolve them at apply time.

### yadm

**Model.** A bare git repo whose work tree is `$HOME`; yadm is a thin git wrapper, so merge and conflict behaviour is git's. On `yadm clone`, "if a file already exists locally and has content that differs from the one in the repository, the local file will be left unmodified and you'll have to review and resolve the differences" ([getting started](https://yadm.io/docs/getting_started)): the join never overwrites.

**Per-machine differences: alternate files.** A file named `path##<condition>[,<condition>...]` is a candidate for `path`. Conditions: `os`, `hostname`, `user`, `arch`, `distro`, `distro_family`, `class` (a free label set with `yadm config local.class Work`, multiple allowed), `default`, plus `template` and `extension`. `~` negates. All conditions must match; templates outrank symlink candidates, then the candidate with more conditions wins. The winner is symlinked to `path` automatically after yadm commands (`yadm.auto-alt`) or by `yadm alt` ([alternates](https://yadm.io/docs/alternates)). Per-machine choice is data in file names, not logic in file bodies.

**Secrets.** Patterns in `~/.config/yadm/encrypt` select files; `yadm encrypt` bundles all matches into one archive (`~/.local/share/yadm/archive`), which is committed; `yadm decrypt` restores them and strips group/other permissions. Default is symmetric GPG; `yadm.gpg-recipient` switches to public-key; `yadm.cipher openssl` swaps the cipher. git-crypt and transcrypt also work through yadm. The docs still recommend a private repo "even though they are encrypted" ([encryption](https://yadm.io/docs/encryption)). The single-archive design means any change to any secret rewrites one opaque blob, so two machines editing different secrets always conflict.

### git-crypt and SOPS: encryption inside a git repo

**git-crypt** ([README](https://github.com/AGWA/git-crypt)) uses git clean/smudge filters selected by `.gitattributes` (`secret filter=git-crypt diff=git-crypt`): files are encrypted on commit, decrypted on checkout. Keys are shared via `git-crypt add-gpg-user` (the repo key encrypted to each GPG user, stored in the repo) or `git-crypt export-key` (a symmetric key file carried out of band, then `git-crypt unlock <keyfile>`). Documented limits: no revocation (anyone with an old key keeps history), file names, commit messages and sizes are not hidden, and "git-crypt does not hide when a file does or doesn't change ... or the fact that two files are identical" (deterministic encryption, which is what makes it git-friendly).

**SOPS** encrypts *values*, not files ([encryption protocol](https://github.com/getsops/docs/tree/main/content/en/docs)): each file gets a random 256-bit data key, which is encrypted to every configured master key (age, PGP, cloud KMS) and stored in the file's `sops` metadata. Each leaf value is encrypted with AES256-GCM under the data key with its own IV, and the concatenated key path is used as AEAD additional data, so values cannot be moved between keys. Keys stay in plaintext so diffs show which setting changed. `.sops.yaml` `creation_rules` with `path_regex` choose recipients per path; `sops updatekeys` re-wraps the data key for a changed recipient list without rotating it; a `diff=sopsdiffer` gitattribute with `textconv = "sops decrypt"` gives plaintext `git diff`. A MAC over all values, stored encrypted under `sops.mac`, detects added or removed values.

**The merge cost of the MAC.** Because every edit rewrites `mac` and `lastmodified`, two branches that touched *different* keys still conflict on those lines, and neither side's MAC is valid for the merged file. This has been an open complaint since the project began ([sops#52](https://github.com/getsops/sops/issues/52), [sops#1117](https://github.com/getsops/sops/issues/1117), [sops#1712](https://github.com/getsops/sops/issues/1712)). The workaround in the ecosystem is a custom git merge driver that decrypts base/ours/theirs, three-way merges the plaintext maps, and re-encrypts ([Clef merge driver](https://docs.clef.sh/guide/merge-conflicts)).

---

## Git-transport knowledge vaults

### obsidian-git

**Model.** An Obsidian plugin that runs "commit-and-sync": stage everything, commit, pull, push, on an interval (the interval persists across sessions, so a short Obsidian session still triggers the overdue run) ([docs](https://github.com/Vinzent03/obsidian-git/tree/master/docs)). The docs are blunt that "Git/GitHub is not a syncing service".

**Merge semantics.** `syncMethod` is `merge`, `rebase` or `reset`; a separate "Other sync service" pull mode only moves `HEAD` without touching files, for users whose files are already moved by Obsidian Sync or iCloud. On conflicts, the plugin shows "You have conflicts in N files", writes and opens a conflict note listing them, and refuses to push while any remain (`Cannot push. You have conflicts...`) ([main.ts](https://github.com/Vinzent03/obsidian-git/blob/master/src/main.ts)). Conflict markers land in the user's notes; resolution is manual.

**Limits.** Mobile uses isomorphic-git (no native git on Android/iOS): no SSH, no rebase, and the author calls it "very unstable". Removing a file from sync requires `git rm --cached`; changing `.gitignore` after commit does nothing. No encryption.

### Obsidian Sync (vendor cloud)

**Merge semantics** ([troubleshoot](https://obsidian.md/help/sync/troubleshoot)): Markdown is merged with Google's diff-match-patch; every other file (canvases included) is "last modified wins"; settings JSON is merged by applying local keys over remote keys. Since 1.9.7 the user may instead choose "Create conflict file", producing `note (Conflicted copy <device> <YYYYMMDDHHMM>).md`. That choice is per device.

**First join.** Connecting a device whose vault already has notes is "not recommended"; the user is warned that local notes will be merged, and is advised to adjust sync settings before the first sync ([setup](https://obsidian.md/help/sync/setup)).

**Per-machine differences.** Selective sync (excluded folders, file types, which config categories sync) is configured per device and itself never syncs ([settings](https://obsidian.md/help/sync/settings)). A device can point Obsidian at a different config folder (e.g. `.obsidian-mobile`) to keep an entirely separate settings set in the same synced vault ([configuration folder](https://obsidian.md/help/configuration-folder)). Each device has a user-assigned name used in the sync log.

**Deletions and history.** Deleted files are recoverable from Settings → Sync → Deleted files; note versions are kept 1 month (Standard) or 12 months (Plus), attachments two weeks ([version history](https://obsidian.md/help/sync/version-history)).

**Secrets.** The remote vault is end-to-end encrypted with a vault password separate from the account password, possibly different per vault.

### Logseq

Logseq's legacy file sync used an age-based encryption library (`lsq-encryption` in [rsapi](https://github.com/logseq/rsapi)). The DB version abandoned file-level sync: syncing a live SQLite database as files corrupts graphs (WAL files, per-device client-ops state) and cannot merge concurrent edits, so it moved to an operation-based "RTC" sync where clients keep local `client-ops` and a server reconciles them; a self-hosted local-token mode was merged on 2026-09-21 ([PR #13117](https://github.com/logseq/logseq/pull/13117)). The lesson generalises: a live database file is not a sync unit; either sync operations or sync a deterministic export.

---

## Peer-to-peer file sync

### Syncthing

**Data model** ([BEP v1](https://docs.syncthing.net/specs/bep-v1.html)). Each device keeps an index of `FileInfo` records per folder. `version` is a version vector (counters keyed by the first 64 bits of each device ID); `sequence` is a device-local monotonic clock; `deleted` marks a tombstone (empty block list, modification time = deletion time). Folder + name + version identify a file's content at a point in time, with no central authority.

**Conflicts** ([syncing](https://docs.syncthing.net/users/syncing.html)). Concurrent version vectors with differing content produce a conflict. The file with the older modification time loses and is renamed `<name>.sync-conflict-<date>-<time>-<modifiedBy>.<ext>`; ties go by device ID. For modify-versus-delete, "if the deletion wins the conflict resolution, the file is renamed to a conflict copy": a winning delete still never discards modified content. `maxConflicts` (default 10) caps copies per file ([config](https://docs.syncthing.net/users/config.html)). Writes go through temporary files; the watcher batches changes for 10 s and holds deletions for an extra minute.

**Deletion safety.** The folder marker `.stfolder`: if it is missing (unmounted disk, wrong path), Syncthing treats the folder as broken and stops syncing it instead of broadcasting every file as deleted ([FAQ](https://docs.syncthing.net/users/faq.html)). `ignoreDelete` makes a device ignore incoming deletes but is "highly discouraged". Versioning (trash can, simple, staggered, external) keeps local copies of replaced or deleted files; the FAQ still says Syncthing "is not a great backup application because all changes ... will be propagated to all your devices."

**Per-machine differences.** `.stignore` never syncs, but can `#include` a file that does, so shared and local ignore rules compose; `(?d)` lets an ignored file be deleted when it blocks a directory delete ([ignoring](https://docs.syncthing.net/users/ignoring.html)). Folder types express role: send-only (with "Override Changes" to force this device's state on the cluster), receive-only (with "Revert Local Changes"), send-receive, and receive-encrypted ([folder types](https://docs.syncthing.net/users/foldertypes.html)).

**Secrets / untrusted storage.** Receive-encrypted folders let a device store data it cannot read: contents, names and structure are encrypted (XChaCha20-Poly1305 and AES-SIV, keys from scrypt over folder password + folder ID); sizes remain visible. Still documented as "beta / testing only" ([untrusted devices](https://docs.syncthing.net/users/untrusted.html)).

---

## Record-log sync

### Atuin

**Model.** Everything (history, KV, aliases, vars, scripts) is a record in one store ([AGENTS.md](https://github.com/atuinsh/atuin/blob/main/AGENTS.md)). Records form append-only series keyed by `(host, tag)`, each with a monotonic `idx`.

**Merge semantics.** The sync diff compares, per `(host, tag)` series, the local and remote highest `idx`: local ahead → upload, remote ahead → download, equal → noop, only one side has it → copy it over ([record/sync/mod.rs](https://github.com/atuinsh/atuin/blob/main/crates/atuin-client/src/record/sync/mod.rs)). There is no conflict resolution because there can be no conflict: only one host ever writes a given series. Operations are sorted by host and tag so the same input gives the same plan.

**Deletions.** A delete is a record: `HistoryRecord::Delete(HistoryId)` appended to the series, applied on other machines by `delete_rows` during incremental build; records created and later deleted are never committed to the local history table ([history/store.rs](https://github.com/atuinsh/atuin/blob/main/crates/atuin-client/src/history/store.rs)).

**First join and secrets.** A new machine runs `atuin login -u <user> -p <password> -k <key>`; the encryption key lives under `~/.local/share/atuin` and never goes to the server, so the account password and the data key are separate secrets ([sync docs](https://docs.atuin.sh/latest/reference/sync/)). Since 2023 each record is sealed with PASETO v4 local (XChaCha20-Poly1305 + Blake2b) under a random per-record content key wrapped by the master key, with `id, idx, version, tag, host` authenticated as implicit assertions; the move away from one-key NaCl secretbox was motivated partly by the lack of key rotation ([new encryption](https://blog.atuin.sh/new-encryption/)).

---

## Vendor settings sync

### VS Code Settings Sync

**Merge semantics.** A three-way merge per resource against the last-synced base. For settings, `merge(local, remote, base, ignoredSettings, resolvedConflicts, ...)` computes base→local, base→remote and local→remote key diffs; a key changed differently on both sides is a conflict, and comments/formatting are preserved by editing the JSON tree ([settingsMerge.ts](https://github.com/microsoft/vscode/blob/main/src/vs/platform/userDataSync/common/settingsMerge.ts)). Extensions merge the same way: an extension in base and remote but absent locally was uninstalled locally and is removed from remote; one in base and local but absent remotely was uninstalled elsewhere and is uninstalled here; enable/disable state is part of equality ([extensionsMerge.ts](https://github.com/microsoft/vscode/blob/main/src/vs/platform/userDataSync/common/extensionsMerge.ts)). Base-relative absence is how deletions are inferred; no explicit tombstone.

**Conflicts in the UI.** "Accept Local" / "Replace Remote", "Accept Remote", or "Show Conflicts" into a diff editor and "Complete Merge" ([settings sync](https://code.visualstudio.com/docs/configure/settings-sync)).

**Per-machine differences.** Two layers: extension authors declare settings with `scope: machine` or `machine-overridable`, whose values "will not be synchronized" ([contribution points](https://code.visualstudio.com/api/references/contribution-points)); users add keys to `settingsSync.ignoredSettings` and extensions to `settingsSync.ignoredExtensions`. Ignored settings are carried through the merge untouched on each side. `settingsSync.keybindingsPerPlatform` keeps keybindings per OS.

**Machine identity and recovery.** A "Synced Machines" view lists devices by a default name (OS + Stable/Insiders), lets the user rename them or turn sync off on another machine remotely. Local backups are kept 30 days, remote history keeps the latest 20 versions per category, both browsable and restorable.

### JetBrains Backup and Sync

Settings are stored in the JetBrains Account; categories (UI, code, tools, system) are selectable; plugins sync their enabled state, and a plugin present on one IDE is installed on the other unless disabled ([docs](https://www.jetbrains.com/help/idea/sharing-your-ide-settings.html)). First join is an explicit either/or: "Push Settings to Account" or "Get Settings from Account", no merge. The older git-based Settings Repository plugin (deprecated, unbundled, still on Marketplace) offered the same trio as buttons: Overwrite Local, Overwrite Remote, Merge ([Settings Repository](https://www.jetbrains.com/help/idea/settings-tools-settings-repository.html)); its YouTrack history is mostly about those buttons misbehaving.

---

## Mass-deletion protection in consumer sync

**OneDrive** ([sync app policies](https://learn.microsoft.com/en-us/sharepoint/use-group-policy)): by default, deleting more than 200 synced files "within a short period of time" pops a notification offering to continue removing the cloud copies or restore the local files (`LocalMassDeleteFileDeleteThreshold`, 0–100000). With `ForcedLocalMassDeleteDetection`, the warning cannot be dismissed permanently and "if a user doesn't confirm a delete operation within seven days, the files aren't deleted". A separate first-delete reminder ("Deleted files are removed everywhere") explains propagation until the user dismisses it.

**Dropbox**: a mass deletion (by count or size) triggers an email summarising what was deleted, by whom and when, with a restore link; deleted files are recoverable for 30 days or longer by plan, and Rewind rolls a whole account or folder back to a point in time ([recover deleted files](https://help.dropbox.com/delete-restore/recover-deleted-files-folders)).

Both treat a large delete as probably accidental, hold it (OneDrive) or make it cheap to undo (Dropbox), and tell the user out of band.

---

## AI-agent config tools

### cc-switch

A Tauri desktop app (136k stars, the most-starred tool in this survey) that manages providers, MCP servers, prompts and skills for Claude Code, Codex, OpenCode and others in a local SQLite database. Sync is **whole-snapshot, manual direction** over WebDAV or S3, or by pointing the config directory at Dropbox/OneDrive/iCloud/NAS ([README](https://github.com/farion1231/cc-switch)).

- **Remote layout** ([sync_protocol.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/sync_protocol.rs)): `db.sql` (a database export), `skills.zip` (a deterministic zip of the skills tree) and `manifest.json` with `format: "cc-switch-webdav-sync"`, protocol `version: 2`, `db_compat_version`, `device_name`, `created_at`, per-artifact SHA-256 and size, and a `snapshot_id` derived from the artifact hashes.
- **Merge semantics**: none. "Upload" overwrites remote; "Download" shows the remote snapshot's protocol version, DB version, timestamp and size, asks for confirmation, and makes a safety backup of the local database before overwriting ([settings manual](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/1-getting-started/1.5-settings.md)). Auto-sync uploads on an interval; turning it on or off requires confirmation. A global mutex serialises every upload/download across transports.
- **Per-machine data**: local-only tables are excluded from the snapshot and do not trigger auto-sync: `proxy_request_logs`, `provider_health`, `session_log_sync`, `model_pricing`. The "sync-aware backup" variant skips local-only tables ([v3.12.0 notes](https://github.com/farion1231/cc-switch/blob/main/docs/release-notes/v3.12.0-en.md), 2026-03-09).
- **Secrets**: no encryption in the sync layer; API keys travel inside `db.sql` in plaintext, protected only by the WebDAV/S3 account.
- **Failure reports**: WebDAV incompatibilities dominate the issue tracker (NAS returning 400 on MKCOL for existing directories, 302-redirecting servers, SOCKS5 proxies) ([#5621](https://github.com/farion1231/cc-switch/issues/5621), [#5416](https://github.com/farion1231/cc-switch/issues/5416), [#7393](https://github.com/farion1231/cc-switch/issues/7393)).

### rulesync and AIS

**rulesync** generates per-tool files (rules, commands, MCP, ignore, subagents, skills for 50+ tools) from one `.rulesync/` source, with a global `~/.rulesync` mode and `rulesync fetch` to pull rules from a remote repo ([README](https://github.com/dyoshikawa/rulesync)). Cross-machine sync is whatever git does with `.rulesync/`; it has no merge, delete or secret handling of its own.

**AIS** clones asset repos into `~/.config/ai-rules-sync/repos/` and symlinks entries into projects, with shared (`ai-rules-sync.json`), private (`ai-rules-sync.local.json`) and global (`user.json`) manifests; `ais install` restores all links on a new machine ([README](https://github.com/lbb00/ai-rules-sync)). Updates propagate by `git pull` in the cache. Small (38 stars) but a clean example of splitting a committed manifest from a machine-local one.

---

## Summary comparison

| | Merge unit | Concurrent edit | Delete representation | First join | Per-machine | Secrets |
| --- | --- | --- | --- | --- | --- | --- |
| chezmoi | git text (rebase) | git conflict; prompt on local drift | explicit `remove_`, `exact_`, `.chezmoiremove` | clone → diff → apply; config template prompts once | templates + local `[data]`, templated ignore, `create_`/`modify_` | age/gpg/git-crypt/transcrypt files; password-manager lookups |
| yadm | git text | git conflict | git delete | clone leaves differing local files untouched | `##` alternate file names, `class` | one GPG/OpenSSL archive |
| git-crypt / SOPS | file / value | opaque / MAC lines always conflict | git delete | key via GPG or exported key file | SOPS path rules | deterministic file / per-value AEAD |
| obsidian-git | git text | conflict markers, push blocked | git delete | clone | `.gitignore` | none |
| Obsidian Sync | file | md merged, others last-modified-wins, or conflict copy | deleted-files bin | warns, then merges | per-device selective sync, per-device config folder | E2E vault password |
| Syncthing | file + version vector | older mtime renamed to conflict copy | `deleted` flag in index | merge by same rules | local `.stignore` + `#include`, folder types | receive-encrypted (beta) |
| Atuin | record in per-host series | impossible by construction | delete record | login with key | per-host series | per-record wrapped key |
| VS Code | per-key 3-way vs base | per-key conflict, diff editor | absence vs base | auto-merge | `machine` scope, ignored lists | account-bound cloud |
| JetBrains | category | last writer | — | push or get, no merge | category toggles | account-bound cloud |
| cc-switch | whole snapshot | last manual upload wins | implicit in snapshot | download with backup | local-only tables | plaintext in snapshot |

---

## Patterns and trade-offs

**Where the field converges**

- **The shared state is not the rendered state.** chezmoi (source vs target), yadm (alternates), VS Code (`machine` scope) and cc-switch (local-only tables) all keep one shared description and let each machine derive or withhold part of it. Nobody ships "every machine byte-identical" once real users arrive.
- **Machine-local choices live outside the synced data.** chezmoi's config file, Syncthing's `.stignore`, Obsidian's selective-sync settings and VS Code's ignored-settings list are local by design; the setting that decides what syncs never itself syncs (or syncs only by explicit include).
- **Secrets are encrypted before they reach the transport, and the key travels out of band.** age/GPG recipients (chezmoi, SOPS), exported key files (git-crypt), a separate key argument at login (Atuin), a vault password separate from the account (Obsidian). The remote account credential and the data key are two different secrets everywhere except cc-switch.
- **Deletes need an explicit representation or a base.** Syncthing and Atuin write tombstones; VS Code infers deletion from absence relative to the last-synced base; chezmoi requires an explicit remove entry. Plain "missing from the snapshot" is used only by whole-snapshot tools, which is exactly where accidental mass deletes come from.
- **Mass deletes are treated as suspect.** Syncthing's folder marker, OneDrive's 200-file prompt with a seven-day hold, Dropbox's email plus 30-day recovery: the common idea is that "everything disappeared" is more likely a broken mount or a bad checkout than intent.

**Where it splits, and why**

- **Merge granularity.** Text-line (git tools), key-level three-way (VS Code, Obsidian settings JSON, the SOPS merge-driver workaround), file-level with conflict copies (Syncthing, Obsidian non-markdown), and none (cc-switch, JetBrains). Finer granularity needs a base version and a structured format; tools that store opaque blobs (yadm archive, git-crypt files, SOPS MAC) lose it.
- **Conflict outcome.** Stop and ask (git tools, VS Code, chezmoi drift prompt) versus keep both (Syncthing, Obsidian conflict-file mode) versus pick one silently (last-modified-wins). Unattended tools pick "keep both"; interactive tools pick "stop and ask".
- **Avoiding conflicts structurally.** Atuin gives each host its own append-only series, so there is nothing to merge. Syncthing's send-only / receive-only folders assign a writer role per device. Everyone else accepts concurrent writers and resolves after the fact.
- **First join.** Merge silently (VS Code, Syncthing), warn then merge (Obsidian), never overwrite local (yadm), preview then apply (chezmoi), or force an explicit direction (JetBrains, cc-switch). Tools that merge silently are also the ones with good conflict copies or history; tools without either force a direction.

## Worth borrowing / worth avoiding

**Worth borrowing**

- A three-way merge against the last-synced base, per key, for structured config (VS Code). It turns "absent" into a meaningful signal (deleted here vs never seen) without separate tombstones, and it only raises conflicts where both sides really diverged.
- A folder-health marker before trusting an empty or shrunken tree (Syncthing `.stfolder`), and a count threshold that holds a large delete for confirmation instead of propagating it (OneDrive's 200 files, seven-day hold).
- When a delete races a modification, keep the modified content somewhere visible rather than letting the delete win outright (Syncthing's conflict copy even when the delete wins).
- Single-writer series for data that is naturally per machine (Atuin): logs, activity, per-host state never conflict if only their host writes them.
- A join-time questionnaire that asks each machine-specific value once and stores it locally (chezmoi `.chezmoi.toml.tmpl` + `promptStringOnce`), and a join that previews before it writes (`chezmoi diff`) or leaves differing local files alone (yadm).
- Declaring machine-only fields at the schema level rather than in a user-maintained ignore list (VS Code `scope: machine`), with a user ignore list on top for exceptions.
- Encrypting per value under a wrapped data key, with the key path as AEAD associated data (SOPS, Atuin): readable diffs, values that cannot be swapped, and recipient changes that re-wrap one key instead of re-encrypting everything.
- A snapshot manifest that records protocol version, schema version, originating device and content hashes (cc-switch), so a machine can refuse or warn on an incompatible or unexpected remote before applying it.
- A safety backup of local state immediately before any apply that overwrites it (cc-switch, VS Code local backups).
- Naming devices and showing them in one list, with a way to detach one remotely (VS Code Synced Machines, Obsidian device names).

**Worth avoiding**

- Plaintext secrets in the synced payload, protected only by the storage account (cc-switch's `db.sql`).
- Whole-snapshot last-writer-wins for anything two machines might both edit: one stale upload silently erases the other machine's work (cc-switch, JetBrains' push/get).
- Opaque encrypted bundles as the merge unit (yadm's single archive, git-crypt files, SOPS's file-wide MAC): every concurrent edit becomes a conflict nobody can resolve in a text editor. If encryption is needed, encrypt per value, keep keys/paths in plaintext, and keep integrity checks from rewriting shared lines on every edit.
- Syncing a live database file (Logseq's reason for abandoning file sync); sync a deterministic export or operations instead.
- Conflict markers written into user content with no tool to resolve them, and a mobile or secondary client that cannot run the full algorithm (obsidian-git on isomorphic-git).
- An "ignore incoming deletes" escape hatch (Syncthing's discouraged `ignoreDelete`): it trades one kind of divergence for another that never heals.
- Auto-push without a secret check (chezmoi's own warning about `autoPush`).
