# Spec 010 — Research

> 中文版: [research.zh.md](./research.zh.md)

Decision rationale lives in
[ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md) and the
constitution 0.3.0 amendment. This file records the background and the options
weighed.

## Problem

A single user runs Coffer on several machines; each vault diverges. The
constitution forbade a vendor cloud as system of record, so sync was a non-goal
until a bounded amendment allowed a **user-owned** medium.

## Transport options

| Option                         | History/merge | Local-first fit | Conflict handling | Verdict |
| ------------------------------ | ------------- | --------------- | ----------------- | ------- |
| **User-owned git repo**        | built-in      | strong (user owns remote) | git 3-way + per-file granularity | **chosen** |
| Peer-to-peer (Syncthing-style) | none          | strongest       | last-writer-wins, no history | deferred |
| User-owned object store (S3)   | none          | strong          | weak              | rejected |
| Hosted Coffer service          | n/a           | violates Principle I | n/a          | rejected |

Git wins for a developer audience: they already have git credentials, and we get
diff/history/merge for free.

## Why a separate workspace + export/import (not commit the live dir)

`coffer.db` is binary and unmergeable, and the live runtime dir mixes truth
(knowledge/memory files) with rebuildable/local state (db, logs, daemon.json).
A dedicated workspace with a text export keeps git diffs meaningful and lets
SQLite remain the local system of record. Knowledge/memory are already files, so
they mirror directly; config and credentials are projected to text.

## Why ciphertext-only + out-of-band key

Putting the master key in the repo would make the ciphertext pointless and
violate the amendment. Exporting only ciphertext means even a GitHub-hosted
remote holds nothing usable. The one-time per-machine key bootstrap is the
accepted cost; until the key is present, ciphertext is reported as locked rather
than silently failing.

## Why manual default + opt-in auto

A single user is usually on one machine at a time, so manual `coffer sync` is
predictable and conflict-light. Auto-sync (debounced push + interval pull) is
offered for hands-off convergence but stays opt-in to avoid surprise background
network and surprise conflicts.

## Determinism

Clean merges depend on stable serialization: sorted keys, normalized timestamps,
and excluding machine-local fields (`id`, `created_at`, `updated_at`). This is
unit-tested because it is load-bearing for the whole merge story.
