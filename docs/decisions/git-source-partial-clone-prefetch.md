# A Git Skill's Folder Is Fetched in One Request From a Partial Clone, With One Full-Clone Fallback

**Status**: Accepted
**Date**: 2026-11-03
**Deciders**: Yuxing (owner), Claude
**Related**: [Each CLI Command Waits as Long as Its Route Needs](cli-request-wait-budgets.md), spec skill-manager "Fetch a Git skill's folder in one request, within one deadline", [git 2d2da172](https://github.com/git/git/commit/2d2da172f37f5a406a0f5a099cd268bcb1bd7d42)

## Context

Coffer reads a skill's repository by cloning it into staging with `--no-checkout --filter=blob:none`, resolving the ref, and checking out only the skill's folder with `git checkout <commit> -- <subpath>` into a separate work tree with its own index. The partial clone keeps every commit and tree — an update check counts the commits since the pin that touch the folder, and the hand-off lists them — without downloading every version of every file.

On 2026-11-03 importing `cathrynlavery/diagram-design` (`skills/diagram-design`, 290 files) failed on the owner's Mac (Apple Git 2.50.1). The clone took about 1 s; the checkout ran 30 s and exited 128 with `You are attempting to fetch 3eb03b8…, which is in the commit graph file but not in the object database` and `could not fetch c8faff0… from promisor remote`. A plain `--depth 1` clone of the same commit worked, and so did the failed partial repository with `-c core.commitGraph=false`, in 146 s.

Reproduced on git 2.43 (Linux): the same checkout succeeded but took **96 s**, printing "Auto packing the repository in background" over and over. A checkout limited to a path does not prefetch the blobs it needs (only a whole-tree checkout batches them), so every missing file is a separate lazy fetch — one network round trip each — and each fetch can start a background auto gc that repacks and rewrites the commit-graph while the next fetch runs. Git's guard against a commit that is in the commit-graph but missing from the object store (2d2da172, added for an endless lazy-fetch loop in partial clones) is the error the Mac printed. The exact interleaving on Apple Git was not traced; the fix removes both preconditions, the per-file fetches and the background maintenance.

Fetching the folder's missing objects in one request first — listed with `git rev-list --objects --missing=print <folder tree>`, which fetches nothing, then `git fetch --stdin` with the same flags git's own lazy fetch uses — took **0.53 s**, and the checkout after it 0.05 s, with all 290 files and the same content hash as the plain clone (`bb1a239d…`).

How comparable tools fetch part of a repository: GitHub Actions' checkout and Scalar use `--filter=blob:none` with a whole-tree or sparse checkout, which git prefetches in one batch; many skill and plugin installers use `--depth 1`, which drops the history Coffer's update check needs.

## Options Considered

### Option A — Keep the partial clone, prefetch the folder in one request, fall back once to a full clone (chosen)

Before the checkout, list the folder's missing objects and fetch them with one `git -c fetch.negotiationAlgorithm=noop fetch --no-tags --no-write-fetch-head --recurse-submodules=no --filter=blob:none --stdin origin`. Run every git command with `gc.auto=0`, `maintenance.auto=false` and `fetch.writeCommitGraph=false`; the clones are temporary and need no upkeep. If the prefetch or the checkout still reports a missing object (a promisor fetch failing, an object not in the database), clone once more without the filter beside the first clone and check out from that; log it. Any other failure — a path the commit does not hold, a network error — is reported as before, with no second clone.

- Good: one round trip instead of one per file (96 s → under 1 s here); a large skill collection still downloads only the folder asked for; the history stays for update checks; the fallback covers a server or git version where the batched fetch still misbehaves, and costs nothing when it is not needed.
- Cost: three more git commands per checkout (a tree lookup, the listing, the fetch), all local but the fetch; the fallback pattern-matches git's wording for a missing object, which a future git could change (then the original error is reported, as today).

### Option B — Always clone in full, no filter

- Good: simplest; no partial clone code path at all.
- Lost because a skills monorepo is cloned whole — every version of every file — to read one folder, every time a skill is added, checked or changed. The bandwidth and time grow with the repository, not the skill.

### Option C — `--depth 1`

- Good: fastest first clone; what many installers do.
- Lost because the update check and the merge hand-off need the commits between the pin and the new head; a shallow clone has none of them, and deepening it per check reintroduces the per-object fetching.

### Option D — Sparse checkout of the folder and a whole-tree checkout

Configure a sparse cone for the folder in the temporary clone and run a full checkout, which git prefetches in one batch.

- Good: git's own batching path.
- Lost because it adds sparse-checkout configuration and work-tree state to a clone Coffer otherwise leaves untouched (it uses a separate index precisely so the clone is never modified), and sparse-checkout behaviour differs across the git versions Coffer supports (2.40 and later).

### Option E — Leave the checkout as it was and disable the commit-graph

Run the checkout with `-c core.commitGraph=false`.

- Good: one flag; it made the failed repository succeed.
- Lost because it keeps one network round trip per file (146 s on the Mac for this skill) and only sidesteps the symptom git happened to report.

## Decision

A skill's repository is cloned partial. Before a checkout, `GitSource.prefetch` fetches every object the folder lacks in one request; git runs with no auto gc, maintenance or commit-graph writes. A missing-object failure after that falls back, once, to a clone without the filter. One operation on a Git source is held to 300 s in all (`GIT_OPERATION_DEADLINE_S`); a cancelled git call kills its process.

A change to how a skill's files are read MUST keep the folder's files to one fetch, and MUST NOT rely on the user's global git configuration being changed.

## Consequences

- Adding or checking a Git skill takes about as long as one clone plus one fetch, whatever the folder's file count.
- The fallback, when it happens, is visible in the daemon log as `skill.git.partial_clone_fallback` with git's message, so a server or git version that needs it can be recognised.
- Enforced in `backend/coffer/infrastructure/skill/git_source.py`, `application/skill/source_service.py`, and `tests/integration/infrastructure/skill/test_git_source_partial.py`, which serves the filter over `file://` and counts promisor packs to prove one fetch.
