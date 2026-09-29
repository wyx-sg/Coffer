## Context

A skill reached Coffer only through `POST /skills/import {path}`: validate the folder, copy it into
`~/.coffer/skills/<name>/`, register the row, deliver. Archives and Git repositories need two
things that path never had: a place to look at content before it is trusted, and — for Git — a
record of where the content came from precise enough to ask "is there something newer".

## Decisions

### 1. One staging registry for every source

`application/skill/staging.py` holds staged sources in memory, keyed by a random id, each owning a
directory under one per-daemon temp root (`tempfile.mkdtemp(prefix="coffer-skill-staging-")`,
never inside `~/.coffer`, so vault sync can never see it). A stage answers what it found; a
confirm registers the chosen skills and removes the directory; a cancel (`DELETE`) removes it; a
stage older than an hour is swept on the next stage. Restarting the daemon forgets every stage,
which is correct: nothing was promised. The same registry holds an update preview (decision 6),
so the web UI has one "close the dialog" call for both.

*Rejected:* writing straight into the master store behind a "pending" row. It would make an
unconfirmed skill visible to delivery, sync and the reconciler, which is exactly what the spec
forbids.

### 2. Where a skill is found

`domain/skill/discovery.py`: the root itself when it holds `SKILL.md`; otherwise every direct
child directory that does (hidden entries and `__MACOSX` skipped); otherwise nothing, with the
reason naming both places. The same rule serves archives, the Git subpath and a staged folder, so
the web folder source also finds `release-notes-main/skill/` instead of only saying it is there.
Each candidate is validated by the existing folder validator, and a candidate that fails is shown
with its reason rather than failing the whole stage.

### 3. Archive checks run before extraction

`infrastructure/skill/archive_reader.py` reads the central directory first and refuses the whole
archive for any entry with an absolute path (`/`, `\`, a drive letter), a `..` segment, a
symlink mode, or when the declared sizes already pass 50 MB. It then extracts entry by entry,
counting the bytes actually decompressed, and aborts past the cap — a lying header cannot get
past it. The upload itself is copied to staging in chunks and refused past the cap. Every
refusal is `SKILL_INVALID` (422) with a `reason` and the offending entries in `details`.

### 4. Git runs as the user's own git, without a prompt

`infrastructure/skill/git_source.py` runs `git` as a subprocess (never a shell) with
`GIT_TERMINAL_PROMPT=0`, the askpass variables removed and `GIT_ALLOW_PROTOCOL=file:git:http:https:ssh`
(no `ext::`), no submodules, and a timeout. Unlike vault sync it does **not** pin the user's
global git config away: the whole point is that a repository the developer can already clone
(credential helper, SSH keys, `insteadOf` rules for a company host) can be added, and Coffer
stores no credential of its own. So the answer to "which credentials" is: whatever this
machine's git already has; Coffer adds none and never prompts. Userinfo in a URL is stripped from
every message.

A clone is `--no-checkout --filter=blob:none` (servers that do not support the filter fall back
to a full clone), the ref resolved as a remote branch, then a tag or commit, then the default
branch, and only the subpath is checked out at that commit (`git checkout <sha> -- <subpath>`,
with its own index file). The checked-out subpath is size-capped before discovery.

The URL is not passed through the SSRF guard. A skill's repository is an endpoint the user names
and a `git` subprocess fetches, like the vault sync remote, and a company's own Git host is
usually on a private address; `docs-site/architecture/security.md` lists it with the exempt
endpoints.

### 5. What is pinned, and how an edit is detected

The `git_import` source records `url`, the `ref` asked for (`null` for the default branch), the
`subpath` of the skill folder inside the repository (after discovery, so updates track exactly
that folder), the full `commit` and a `content_hash`: SHA-256 over the sorted relative paths and
bytes of every file in the folder, ignoring `.git` and Coffer's `.coffer.meta.json`
(`domain/skill/content_hash.py`). The master folder is "edited since the pin" exactly when its
current hash differs — no pinned checkout needs to exist to decide it.

### 6. Checking, previewing and applying

- **Check** clones into staging, resolves the ref, and counts the commits in `pinned..latest` that
  touch the subpath. An update is available when there is at least one; a ref that moved without
  touching the folder is recorded as checked and up to date. The result — checked at, last
  success, git's message on failure, latest commit, commit count, files changed, and the commit
  the user chose to keep their edits against — lives in `skill_source_status`, one row per skill,
  machine-local (it is observation, not vault state, so sync never carries it).
- **Preview** checks out the pinned and the new folder side by side in staging and diffs them
  (`difflib`, binary files flagged). If the master's content hash differs from the pin, the
  preview is a conflict and also carries the local changes against the pin; **Compare** reads one
  path's three versions from the staged preview.
- **Apply** validates the new folder (its `SKILL.md` must still name this skill), swaps it in with
  the existing `atomic_replace`, rewrites the source's `commit` and `content_hash`, refreshes
  `version_hash` and the description, clears the kept-edit mark and audits `skill_updated` with the
  commit range. A conflict applies only with an explicit discard (`Take theirs`); otherwise
  `SKILL_UPDATE_CONFLICT` (409). Bindings and links are untouched because the folder name is.
- **Keep mine** records the latest commit as dismissed; the next check offers an update again
  only when a newer commit touches the folder.
- The six-hourly worker checks only skills not checked in the last six hours, so a daemon that
  restarts often does not fetch on every start.

### 7. Requirements are read at request time

`requires` is parsed from the master `SKILL.md` when the read model is built
(`domain/skill/requires.py`), leniently: a list or `{commands: [...]}`, entries as `name`,
`name>=version` or `{command, version}`. Nothing is stored, so an edit in the user's editor shows
at once. Probing a command (installed, version, login) is the CLIs page's work and is not done
here.

### 8. The Skills page is a library beside a reading pane

The boards draw the list and the open skill side by side, so `/skills` and `/skills/<name>/<tab>`
render the same page: the list on the left (search, All / On / Off, multi-select with bulk reach
and delete), the detail on the right, resizable with the shared `SplitView`. Delivery's per-agent
states are derived in the client from the skill's bindings, the agents list and, after Check
again, the drift report — no new read route. History renders an empty state until the vault
records skill versions. Unmanaged skills stay on the agent's Skills tab.

## Risks

- A clone of a very large repository can take long; the partial clone and the timeout bound it,
  and the dialog shows progress as "Cloning…".
- `git checkout` writes symlinks the repository contains; the validator refuses any that leave the
  skill folder before a byte reaches the master store.
