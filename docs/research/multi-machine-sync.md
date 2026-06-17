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
