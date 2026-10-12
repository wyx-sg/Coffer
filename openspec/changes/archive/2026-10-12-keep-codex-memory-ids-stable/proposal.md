## Why

A Codex memory's hub id came from its bullet's position in its section. When Codex consolidation inserted, removed or reordered a bullet, every bullet after it took over a neighbour's id. On the owner's Mac on 2026-10-12, one sync reported five "updates" that were all a different memory written over an unrelated one, so the copies in Claude Code were overwritten with another memory's text.

## What Changes

- A Codex bullet's source identity is its file, task group, section and content hash, so bullets around it can move without changing it.
- A bullet that is no longer in the hub takes over the identity of the most alike memory its section no longer holds, when they are at least 0.6 alike, so a rewritten bullet is still an update. Any other bullet is a new memory.
- Existing hub entries keep their ids: an unchanged bullet matches its old entry exactly by that rule.
- ADR `codex-memory-identity-is-content-with-rewrite-carry-over` compares the options.
