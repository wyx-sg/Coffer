# Competitive Research — Multi-Machine Config / State Sync

> English: this file · 中文版: [multi-machine-sync.zh.md](./multi-machine-sync.zh.md)
>
> Internal competitive-research report for Coffer's multi-machine sync (spec 010,
> ADR-016). **Date:** 2026-06-16. **Method:** deep-research harness. **Provenance
> caveat:** this run hit an API session limit mid-verification — 1 claim
> (whole-file encryption support) is 3-0 confirmed; the rest are primary-sourced
> from project docs but not re-verified. Flag for a light fact-check.

## 1. Landscape at a glance

Cross-machine config sync splits by **transport** and by **whether it understands
the content** it moves:

| Class                    | Transport       | Understands content?       | Examples                                            |
| ------------------------ | --------------- | -------------------------- | --------------------------------------------------- |
| **Dotfile managers**     | user's git repo | file-level (copy/template) | chezmoi, yadm, dotbot, GNU Stow, rcm, vcsh          |
| **Vendor settings-sync** | vendor cloud    | app-specific               | VS Code Settings Sync, JetBrains Backup & Sync      |
| **AI-config sync**       | git + symlink   | file-level                 | AIS (ai-rules-sync); rulesync (generator, not sync) |
| **Resource reconcilers** | user's git repo | **semantic (reconcile)**   | **Coffer**                                          |

### The players

- **chezmoi** — the gold standard. Source state in a git repo; **per-machine
  differences via Go `text/template`** (`.chezmoi.hostname`, `.chezmoi.os`
  conditionals) with machine-local data in `~/.config/chezmoi/chezmoi.{toml,
yaml,json}`; **whole-file encryption via four backends (age, git-crypt, gpg,
  transcrypt)** — encrypted files travel ASCII-armored (the `encrypted_`
  attribute), decrypted only locally; password-manager integration
  (`onepasswordDocument`) retrieves secrets at _apply_ time rather than storing
  them. [chezmoi.io]
- **yadm** — GPG (default) / OpenSSL encryption of glob-matched files bundled
  into a single committed archive (`~/.local/share/yadm/archive`) via an explicit
  two-step `yadm encrypt` / `decrypt`. [yadm.io]
- **git-crypt** — transparent per-file encryption inside a git repo (mix public +
  private); key distribution via GPG users or an **out-of-band exported symmetric
  key** — never committed. [github.com/AGWA/git-crypt]
- **AIS (`ai-rules-sync`)** — the closest AI-specific peer: syncs agent rules/
  skills/commands/subagents via **git repos + symlinks into projects**
  (git-as-transport + symlink materialization, not file copy). [github.com/lbb00]
- **rulesync** — a config _generator_, not a sync tool; multi-machine consistency
  relies on the surrounding git repo. **MCPM** — global config, **no
  cross-machine sync.** **VS Code Settings Sync / JetBrains** — vendor cloud, not
  user-owned.
- Confirmed: of the six dotfile tools compared by chezmoi, **only chezmoi and
  yadm support whole-file encryption** (dotbot, rcm, vcsh, bare git do not).
  [confirmed 3-0]

## 2. Capability comparison

| Capability               | chezmoi           | yadm        | git-crypt   | AIS      | VS Code Sync | **Coffer**                        |
| ------------------------ | ----------------- | ----------- | ----------- | -------- | ------------ | --------------------------------- |
| Transport                | user git          | user git    | user git    | user git | vendor cloud | **user git**                      |
| Understands content      | template          | file        | file        | symlink  | app          | **semantic reconcile**            |
| Per-machine templating   | ✅ killer feature | partial     | ❌          | ❌       | partial      | **❌ every machine = full state** |
| Secret handling          | age/gpg/PM refs   | gpg archive | transparent | ❓       | cloud        | **✅ Fernet ciphertext-only**     |
| Master key out-of-band   | ✅                | ✅          | ✅          | —        | n/a          | **✅ never synced**               |
| Every machine full state | ✅                | ✅          | ✅          | ✅       | ✅           | **✅ (no central SoR)**           |
| Reconcile vs overwrite   | overwrite         | overwrite   | overwrite   | symlink  | overwrite    | **reconcile**                     |
| AI-agent-aware           | via templates     | ❌          | ❌          | ✅       | ❌           | **✅ native**                     |

## 3. How Coffer compares

**Where Coffer is distinctive.**

1. **Reconcile-not-overwrite is genuinely unique.** Every dotfile manager applies
   at the _file_ level (copy or template-render onto the target). Coffer mirrors
   knowledge/memory/skills _files_ but reconciles config _resources_ through the
   resource service — a semantic merge, not a blind overwrite. No surveyed tool
   does semantic reconciliation of structured config.
2. **Ciphertext-only secrets + master-key-out-of-band matches best practice.**
   This is exactly the chezmoi/yadm/git-crypt model (age/gpg, key never in the
   repo). Coffer is aligned with the gold standard — validation, not a gap.
3. **Git-as-transport, every-machine-full-state** matches the dotfile philosophy
   (the repo is history/transport, not a system of record).

**Where Coffer lags — concrete borrows.**

1. **No per-machine templating (the biggest gap).** chezmoi's defining feature is
   `.chezmoi.hostname` / `.chezmoi.os` conditionals + machine-local data so each
   machine can differ (work vs personal paths, different agents installed).
   Coffer's "every machine holds full state" is too rigid for real multi-machine
   setups. Borrow per-machine overrides/conditionals.
2. **Single medium = git.** Deliberate and fine, but chezmoi/Syncthing offer
   alternatives; worth noting as a conscious constraint.
3. **Apply-time provider refs.** chezmoi's `onepasswordDocument` resolves secrets
   from an external manager at apply time — ties into the credentials report's
   external-provider-ref borrow.

## 4. Key takeaways for Coffer

1. **Lead with reconcile-not-overwrite** — it is the one thing no dotfile manager
   does, and it is the right model for structured config across machines.
2. **Add per-machine templating / overrides** (chezmoi `.hostname`/`.os` model) —
   the clearest functional gap; "every machine = identical full state" breaks for
   real setups that legitimately differ per machine.
3. **Your ciphertext-only + out-of-band-master-key design is best-practice** —
   keep it; it matches chezmoi/yadm/git-crypt.
4. **AIS (`ai-rules-sync`) is the closest AI-specific peer** (git + symlink); your
   resource-reconcile approach is more robust than symlink materialization.

## 5. Sources

Primary:

- chezmoi.io — comparison-table, user-guide/encryption (age), manage-machine-to-machine-differences
- yadm.io/docs/encryption
- github.com/AGWA/git-crypt
- github.com/lbb00/ai-rules-sync (AIS)
- github.com/dyoshikawa/rulesync · github.com/pathintegral-institute/mcpm.sh
- VS Code Settings Sync docs · JetBrains Backup & Sync docs

## Verification update (2026-06-19)

> Light fact-check pass over the four targeted claims flagged by the 2026-06-16
> provenance caveat (1 local headline claim + 3 web claims), plus an independent
> re-verification of the chezmoi encryption-backend list. All hold; no
> corrections needed.

**Lead:** Every targeted claim is confirmed against primary sources — and the
headline reconcile-not-overwrite differentiator is **implemented in code**, not
just spec'd.

### ✅ Confirmed

- **Reconcile-not-overwrite is real, not aspirational.** Config resources are
  reconciled by `(kind, name)` through the kind-agnostic resource service —
  `update_config` + `set_enabled` for existing, `register` for new, `delete` for
  removed-upstream — never a blind file overwrite. `update_config` re-validates
  config, probes credential refs, and runs per-kind cross-version hooks, so it is
  a validated kind-aware reconcile. [`backend/coffer/application/sync/importer.py:71-110`;
  `backend/coffer/application/resource_service.py:206-243`; ADR-016; spec 010]
- **chezmoi whole-file encryption via four backends** — age, git-crypt, gpg,
  transcrypt; encrypted files stored ASCII-armored with the `encrypted_`
  attribute, auto-decrypted only when needed.
  https://github.com/twpayne/chezmoi/blob/master/assets/chezmoi.io/docs/user-guide/encryption.md
- **chezmoi per-machine templating** via Go `text/template` with
  `.chezmoi.hostname` / `.chezmoi.os` conditionals; machine-local `[data]` in
  `~/.config/chezmoi/chezmoi.{toml,yaml,json}`.
  https://www.chezmoi.io/user-guide/manage-machine-to-machine-differences/
- **chezmoi `onepasswordDocument`** retrieves documents from 1Password at _apply_
  time (output cached per uuid); secrets stay in 1Password, not the dotfiles.
  https://www.chezmoi.io/reference/templates/1password-functions/onepassworddocument/
- **Only chezmoi and yadm support whole-file encryption** among the surveyed
  dotfile tools; dotbot, rcm, vcsh, and bare git do not (`✅`/`❌` per chezmoi's
  comparison table). https://www.chezmoi.io/comparison-table/
- **AIS (`ai-rules-sync`)** syncs AI rules/skills/commands/subagents across many
  agents (Cursor, Claude Code, Copilot, OpenCode, Trae AI, Codex, Gemini CLI,
  Warp) by managing rules in git repos and materializing them into projects via
  symbolic links (default targets `.cursor/rules/`, `.github/instructions/`) —
  confirming git + symlink, not file copy. https://github.com/lbb00/ai-rules-sync

### ✏️ Corrected

- **Nuance, not a factual fix (§3.1):** the 3-way _content_ merge happens at the
  git/YAML text layer (deterministic serialization — one YAML per resource,
  sorted keys, normalized timestamps, local-only fields stripped — makes diffs
  mergeable); the importer then reconciles the local SQLite DB _to_ the
  already-merged workspace. The report's "semantic merge, not a blind overwrite"
  framing stands; the merge and the reconcile are two distinct layers.
  [ADR-016; `backend/coffer/application/sync/importer.py:71-110`]
- The chezmoi **FAQ** encryption page lists only age/gpg/rage, but the
  **user-guide/encryption** page names all four backends, matching the report —
  cite the user-guide, not the FAQ, for the four-backend claim.
  https://github.com/twpayne/chezmoi/blob/master/assets/chezmoi.io/docs/user-guide/encryption.md
