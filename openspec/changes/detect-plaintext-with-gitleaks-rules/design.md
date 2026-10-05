## Context

Today's detector is `backend/coffer/infrastructure/secret/plaintext_scan.py`:
`line_hits` (secret-named assignment + five token shapes, minus references,
interpolations, placeholders and code), wrapped as `find_in_text` for the push
check (`application/sync/round_plaintext.py`, injected through
`surfaces/http/sync_wiring.py`) and `mask_line` for the Sync page's masked
context, and re-used with extra server rules by
`infrastructure/secret/plaintext_findings.py` for **Find plaintext keys**. The
move into secrets rewrites a skill file at `Hit.start`/`Hit.end` on
`Finding.line`.

gitleaks v8.30.1 (2026-03-21) is the current release. Its default config has
222 rules (221 with a regex, one path-only), 130 with an entropy threshold, one
`secretGroup`, 9 with rule allowlists (regex targets `secret`/`match`/`line`,
stopwords, paths, one `AND` condition), 5 with a path condition, and a global
allowlist of 25 paths, 13 regexes and 2 stopwords. No rule uses
`[[rules.required]]` (composite rules).

All numbers below come from a prototype run in a scratch directory: a
translator, an executor with gitleaks' semantics (copied from
`detect/detect.go` `detectRule` and `checkFindingAllowed`), and a fictional
vault.

## Goals / Non-Goals

**Goals:** gitleaks-v8.30.1-level detection in all three callers; findings
that name their rule; a reproducible, reviewable path to newer rules; no
gitleaks binary.

**Non-Goals:** git-history scanning modes, baselines, `gitleaks:allow`
comments, report formats.

## Decisions

### D1. Translate RE2 to Python `re` at sync time, not at load time

The sync script writes already-translated patterns, so the shipped file is what
runs and a reviewer sees each translation in the diff. Translation rules (all
222 rules of v8.30.1 pass; 22 needed rule 1):

1. A flag group not at the start (`X(?i)Y`) applies, in RE2, to the rest of
   its enclosing group *across `|`*. It becomes a scoped group reopened after
   each `|`: `(?:a(?i)b|c)` → `(?:a(?i:b)|(?i:c))`. Python rejects the bare
   form.
2. `\z` → `\Z`; `$` outside a class → `\Z` (RE2 without `(?m)` means end of
   text; Python's `$` also matches before a final newline). No rule sets `m`.
3. `[[:alnum:]]` and the other POSIX classes → explicit ranges; a negated POSIX
   class is untranslatable.
4. Compile with `re.ASCII`: RE2's `\w`, `\d`, `\s`, `\b` are ASCII.
5. `\Q…\E`, `\C`, `\p{…}` are untranslatable. An untranslatable rule is listed
   in the file header and the script exits 1; the previous rule file stays.

Rejected: **`google-re2`** (the RE2 binding) would remove translation and give
RE2's linear-time guarantee — 0.17 s on the 1 MB blob below — but adds a native
dependency to four frozen binaries for a gain D3 already gets.

### D2. Executor semantics follow gitleaks, positions follow Coffer

Per file: skip on a global path allowlist; lowercase once for the keyword
pre-filter; for each rule whose keywords appear (and whose `path` matches):
`finditer`, take the secret group (`secretGroup`, else the first non-empty
group, else the match), drop when Shannon entropy over characters ≤ the
threshold, drop on the global then the rule allowlists (`OR` by default: regex
on its target, or a stopword contained in the lowercased secret; `AND`: every
configured check). Unlike gitleaks, the result keeps the secret group's span,
not the match's: `(rule_id, start, end)` as offsets in the text, from which the
line and the column range on that line follow. When several rules find the same
value (`api_key = "sk_live_…"` is both `stripe-access-token` and
`generic-api-key`), it is one finding, named by the first rule in file order
other than `generic-api-key`. A value that spans lines (a
private key) reports its first line; the move rewrites by text offsets, so it
replaces the whole block.

### D3. Run each rule only around its keywords

On a 1 MB single-line base64 blob (an image pasted into a note), a whole-text
scan took **19.8 s**: `sumologic-access-id`'s
`[\w.-]{0,50}?(?i:[\w.-]{0,50}?…)` costs ~8 µs per character in a
backtracking engine. Running a rule only inside windows around its keyword hits
(512 characters before, 4 KiB after, extended to the line end; 64 KiB after for
the multi-line `private-key`; overlapping windows merged, matches de-duplicated
by span) took **0.52 s** on the same blob and returned exactly the whole-text
findings on the vault sample. gitleaks itself pre-filters by keyword per
fragment; this is the same filter at a finer grain.

### D4. Coffer's allowlist and rules sit on top of the imported ones

The imported file is never edited by hand; Coffer's additions live in code next
to the executor and are applied after the imported allowlists.

**Allowlist** (a finding is dropped when its value overlaps one of these on its
line, or the value itself is one):

- `coffer://secret/<32 hex>` and bare `secret/<32 hex>`. The bare form is what
  every resource document's `secret_refs` holds; raw gitleaks flags each of
  them through `generic-api-key` (`"GITHUB_TOKEN": "secret/<hex>"`: 624 of 1,020
  false-positive lines in the sample), which would stop every push of a vault
  with an MCP server.
- `$VAR`, `${VAR}`, `{{…}}`.
- Placeholders: today's `PLACEHOLDER` pattern (a value that *is* `xxx…`,
  `<…>`, `your-…`, `changeme`, `example…`, `dummy…`, `redacted`, …).
  `generic-api-key`'s own 1,446 stopwords already drop a value merely
  *containing* `example`, `test` and the like.
- Code: today's `_is_code` rules (a dotted reference such as
  `process.env.SPACE_TOKEN`, call/index/list punctuation in an unquoted value, a
  bare name a declaration or member assignment gives). A JSON Web Token stays a
  value.
- A line holding `coffer run` (a `--secret ENV=NAME` names a secret).

**Rules** (ids prefixed `coffer-`, shown like any other rule):

- `coffer-password-assignment` — a key containing `password`, `passwd`, `pwd` or
  `passphrase` assigned a value of ≥ 8 characters, no entropy threshold, minus
  an all-lowercase or all-uppercase identifier. gitleaks' `generic-api-key`
  needs ≥ 10 characters and entropy > 3.5, so `DB_PASSWORD=Summer2024!` is
  invisible to it; the old detector caught it.
- `coffer-url-password` — `scheme://user:<value>@host`. No gitleaks rule covers
  a generic URL password.
- `coffer-server-setting` (MCP servers only) — an `env`/header value under a key
  that says password, secret, token, key, auth or authorization, or a
  `Bearer`/`Token` credential, ≥ 8 characters. A server's keys are config, not
  prose, so the key name alone is precise; this keeps today's server scan.

An MCP server entry is scanned as the line `KEY: value`, so the imported rules
see the key as context; a finding whose value lies inside `value` is that key's.

### D5. Keep `generic-api-key` — *to confirm*

Fictional vault: 702 files, 35,662 lines, 2.7 MB (300 knowledge notes, 200
memory notes, 60 skills with a script and a `SKILL.md`, 80 MCP server
documents), 29 kinds of non-secret line a vault really holds (commit hashes,
UUIDs, image digests, `cache_key`, `api_version`, coffer references, env reads,
placeholders, `self.token_cache = …`, `curl -H "Authorization: Bearer $TOKEN"`,
…) and 43 planted secrets (16 vendor tokens generated from their rules, 11
random API keys/client secrets, 6 human passwords, 8 URL passwords, a private
key, a JWT).

| Detector | Found (of 43) | Missed | False-positive lines | Kinds of non-secret line flagged |
|---|---|---|---|---|
| Today's `plaintext_scan` | 18 | 15 vendor, 8 URL, key, JWT | 480 | identifier values (`secret: abc_def_name`) |
| gitleaks v8.30.1, raw | 29 | 6 human passwords, 8 URL | 1,020 | bare `secret/<hex>` refs, 40-hex hash under `key:` |
| gitleaks + Coffer allowlist | 29 | 6 human passwords, 8 URL | 396 | 40-hex hash under `key:` |
| gitleaks without `generic-api-key` + allowlist | 18 | 11 random keys, 6 passwords, 8 URL | 0 | — |
| **gitleaks + Coffer allowlist + Coffer rules** | **42** | 1 (`correcthorsebattery`, an identifier) | 396 | 40-hex hash under `key:` |

The line counts track how often each kind was generated, so the kinds column is
the one to read: with the allowlist, the one kind `generic-api-key` still flags
is a high-entropy hex string assigned to a key-named field — which is also what
a hex API key looks like, so it is left to the person (untick, or Push
anyway). Dropping the rule loses every unprefixed random key (`api_key =
"<32 random>"`, `client_secret: …`), the most common shape in hand-written
scripts. Recommendation: keep it.

### D6. Decoded content is not scanned — *to confirm*

gitleaks decodes base64, hex and percent-encoded segments up to depth 5 and
scans the result. Recommendation: not in this change. A vault is hand-written
text; the encoded credential worth catching (Kubernetes `Secret` data) has its
own rule (`kubernetes-secret-yaml`), and a basic-auth header is caught by the
curl rules. Decoding would add a second offset space — a finding inside a
decoded segment can only point at the whole encoded segment, which the move
into secrets would replace wholesale — and pasted images and lock files are
the base64 a vault does hold, so it would add scan time and false positives
for little recall. It can be added later behind the same executor.

### D7. Rule refresh — *to confirm*

- **Manual, at release**: `make refresh-secret-rules` (like
  `make refresh-prices`) rewrites the file for the pin in the script;
  `--check` exits 1 if it would change. Bumping the pin is a one-line edit
  plus the regenerated file.
- **Scheduled pull request**: `.github/workflows/secret-rules.yml`, weekly and
  on `workflow_dispatch`, compares the pin with gitleaks' latest release; if
  newer, it runs the script at that release, runs the rule tests, and opens a
  PR from `chore/gitleaks-rules-<version>` touching only the rule file, its
  header and the pin. The job's failure (untranslatable rule, failing sample)
  surfaces as a red scheduled run and no PR; it never touches `main`'s checks.
  A PR opened with the default `GITHUB_TOKEN` does not trigger `verify.yml`, so
  its required checks would not run; the workflow uses a fine-grained token
  secret (`RULES_PR_TOKEN`, contents + pull-requests write on this repo) to
  open it, or, without that secret, opens an issue naming the new release
  instead.

Recommendation: both — the scheduled PR to notice, the Make target to run by
hand.

### D8. Tests never put a sample secret in the repository

- **Imported rules:** a seeded generator walks each translated pattern
  (`re._parser`) and builds a match; the test runs it through the executor
  (positive), then shortens the secret group one character below its minimum
  width (negative). The sample exists only in memory. On v8.30.1 this round-trips
  for 212 of 221 regex rules; the other 9 (`airtable-personnal-access-token`,
  `curl-auth-header`, `curl-auth-user`, `facebook-access-token`,
  `kubernetes-secret-yaml`, `nuget-config-password`, `sidekiq-sensitive-url`,
  `slack-config-access-token`, `slack-webhook-url`) need context the generator
  cannot invent (an unescaped `.` meant as a dot, a YAML block, an XML
  attribute) and get hand-written samples adapted from the upstream rule's
  `tps`/`fps`, assembled from string pieces so no line of the test file matches
  the rule. A rule added by a future release without a sample fails the test
  until one is generated or written, which is what makes the scheduled PR safe.
- **Hand-written fixtures** (Coffer's allowlist and rules, the callers) use
  obviously fake values (`hunter2-not-real`, repeated characters behind a real
  prefix, concatenated pieces) that the repository's gitleaks scan does not
  flag; `.gitleaksignore` stays as it is.
- **The rule file** is named `gitleaks.toml`, which gitleaks' own global path
  allowlist (`gitleaks\.toml`) already skips, so the repository's
  `secrets-scan` job does not read its allowlist examples.
- **The sync script** is tested on fixed rule fragments in the test file, never
  the network.

### D9. Performance

Prototype, Python 3.14, M-series Mac, single thread:

| Input | Today | New |
|---|---|---|
| Fictional vault, 2.7 MB / 702 files (a first push or join reads all of it) | 0.20 s | 1.27 s |
| One typical note (~4 KB) | < 1 ms | ~1.8 ms |
| 1 MB single-line base64 blob | — | 0.52 s (19.8 s without D3) |
| 1 MB minified JSON / 1 MB of `key_n=value` lines | — | 0.38 s / 1.11 s |

`generic-api-key` is about half of the time. A round's check reads only the
blobs the remote lacks, so a normal push reads a few files and costs
milliseconds; the whole-vault cost is paid on the first push and on a join, and
scales linearly (~0.5 s per MB). The check already runs off the event loop. The
compiled rules are built once per process.

## Risks / Trade-offs

- [`generic-api-key` still flags some hex hashes] → the person unticks or
  pushes anyway, as today; the finding names the rule so the reason is visible.
- [A future gitleaks release uses syntax D1 cannot translate] → the script and
  the scheduled PR fail loudly; the shipped rules stay at the old release.
- [Translation drifts from RE2 semantics in a way the samples do not catch] →
  every rule's generated sample round-trips through the translated pattern, and
  translation fixtures cover each rewrite rule.
- [Keyword windows miss a match longer than the window] → window sizes exceed
  every bounded rule's width; the unbounded `private-key` gets 64 KiB.
- [`re._parser` is private] → used only in tests; pinned Python minor version.

## Migration Plan

No stored data changes: findings are computed on demand and a round's
`plaintext` record gains a `rule` field (an older record reads it as absent).
Blobs already allowed by **Push anyway** stay allowed.
