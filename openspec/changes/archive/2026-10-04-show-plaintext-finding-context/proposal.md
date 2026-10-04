## Why

When a round refuses to push because a file looks like it holds a plaintext
secret, the Sync page lists only the file, the line and the name the value is
assigned to. The detection can be wrong — an example key, a test value, a line
of code such as `const token = process.env.X` — and only the person can tell,
but the page gives them nothing to tell it by: they have to leave Coffer, find
the file and the line, and guess what changed.

## What Changes

- `GET /api/v1/sync/plaintext/context?path=&line=` returns one place the last
  round found, in its file, computed on demand from the file version the round
  read (nothing is stored): the flagged line with three lines either side,
  every plaintext value on them masked, and each value's shape in its place.
- The value is never returned. Masking replaces every character with `•`, so
  the line keeps its length and the code around it reads as it is; only a
  well-known token format's public prefix (`ghp_`, `sk-`, `AKIA`, a URL's
  scheme) stays visible. The shape gives the length, the kinds of character,
  and a hint when it looks like something other than a secret: a code
  reference (names joined by dots), a placeholder word (`example`, `dummy`,
  `test` …, named), or one or two characters repeated.
- The response says whether the remote holds the file (`added` /
  `modified`), whether the flagged line is already on the remote, and for a
  modified file its change against the remote's copy as a unified diff,
  masked line by line the same way.
- Refused with `SYNC_NO_PLAINTEXT_FOUND` (409) unless the last round is
  `plaintext_found`, and with the new `SYNC_PLAINTEXT_NOT_LISTED` (404) for a
  place the round did not find, so it never reads an arbitrary file.
- The Sync page's plaintext card: each place expands in place to the masked
  lines (line numbers, the flagged line tinted, each masked value
  highlighted), a "New file" / "Changed file" mark, the value's shape in
  words, and for a changed file "Show changes" with the masked diff.

## Impact

- Spec: vault-sync gains "Show a plaintext finding in its file".
- Backend: `domain/plaintext_shape.py`, `mask_line` beside the plaintext scan,
  `application/sync/round_plaintext_context.py`, a route, one error code,
  four schemas.
- Frontend: the plaintext card's places; en and zh copy.
- Docs: the vault-sync guide (en and zh) and the error-code reference.
