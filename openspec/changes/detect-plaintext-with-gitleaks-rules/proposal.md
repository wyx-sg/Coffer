## Why

Coffer's plaintext-secret detection is a handful of hand-written patterns: an
assignment whose name says secret, and five token shapes (GitHub, OpenAI,
Slack, AWS). It runs in three places — the Secrets page's **Find plaintext
keys**, the MCP server config scan behind it, and the check before every
vault-sync push — and it misses almost every vendor credential format. On a
fictional vault sample with 43 planted secrets it found 18; it missed 15 of 16
vendor tokens (Stripe, Anthropic, GitLab, Twilio, …), a private key and a JSON
Web Token, and it flagged identifier-like values assigned to secret-named keys.

gitleaks (github.com/gitleaks/gitleaks, MIT) maintains 222 rules for exactly
this, and this repository's own CI already scans with them. Importing those
rules, pinned to a release, and running them with Coffer's own executor gives
Coffer the same detection without shipping or calling the gitleaks binary, and
lets the rules be refreshed when gitleaks publishes new ones.

## What Changes

- **A bundled rule set.** `scripts/sync_gitleaks_rules.py` downloads
  `config/gitleaks.toml` at a pinned gitleaks release (v8.30.1), translates each
  Go RE2 pattern to Python `re` (mid-pattern flag groups, `\z`, POSIX classes,
  RE2's ASCII `\w`/`\d`/`\s`, RE2's end-of-text `$`), and writes
  `backend/coffer/infrastructure/secret/rules/gitleaks.toml` with a header
  naming the source, release, commit and licence; gitleaks' MIT licence ships
  beside it. A rule that cannot be translated is listed in the header and makes
  the script exit non-zero; nothing is dropped silently. All 222 rules of
  v8.30.1 translate.
- **A rule executor.** One detector runs every rule: its regex, secret group,
  Shannon-entropy threshold, keyword pre-filter, path condition, and the
  rule-level and global allowlists (regexes with their `secret`/`match`/`line`
  target, stopwords, paths, the `AND` condition). Each finding names the rule
  (`stripe-access-token`, `generic-api-key`), the line, and where the value
  sits on it. A rule runs only around its keywords, so one long line cannot
  stall a scan.
- **Coffer's own allowlist** on top of the imported one: a secret reference
  (`coffer://secret/<32 hex>`, and the bare `secret/<32 hex>` a resource
  document's `secret_refs` holds), an interpolation (`$VAR`, `${VAR}`,
  `{{…}}`), a placeholder (`xxx`, `<your-token>`, `changeme`, `example…`, …),
  and code that names a value instead of holding one. Without it every MCP
  server document in the vault trips `generic-api-key` and every push stops.
- **Coffer's own rules** for what gitleaks leaves out on purpose and the old
  detector caught: a value assigned to a password-named key regardless of
  entropy (`DB_PASSWORD=Summer2024!`), a password inside a URL
  (`postgres://app:<value>@db`), and, for an MCP server's `env` and headers, a
  value under a secret-named key or a `Bearer`/`Token` credential.
- **One detector for all three callers.** Find plaintext keys, the MCP server
  scan and the push check all call it. A finding carries its rule id next to the
  key it is assigned to; the Secrets dialog, the Sync page's plaintext card and
  each masked value show the rule. The old patterns and `find_in_text` are
  deleted. Dismissing a finding works as it does today: untick it on the
  Secrets page; **Push anyway** allows the exact blobs.
- **Rule refresh.** `make refresh-secret-rules` rewrites the rule file for the
  pinned release and `--check` says whether it would change; it runs by hand
  before a release, and moving to a newer gitleaks release is a pin bump plus
  the regenerated file.
- **Tests.** Every imported rule gets a positive and a negative sample built at
  test time; Coffer's allowlist and rules, the three callers, and the
  translation (on fixed rule fragments, offline) each have tests. No sample
  secret is written into the repository in a form the repository's own gitleaks
  scan would flag.

## Capabilities

### New Capabilities

### Modified Capabilities

- `secret`: adds "Detect plaintext secrets with the bundled rules"; modifies
  "Move plaintext secrets in managed resources into the store" so the scan
  uses those rules and a finding names its rule.
- `vault-sync`: modifies "Refuse to push a plaintext secret" and "Show a
  plaintext finding in its file" so the push check uses the same rules and
  each place and masked value names its rule.

## Impact

- Backend: `infrastructure/secret/` (new `rules/` data, executor, Coffer
  allowlist and rules; `plaintext_scan.py` keeps only the citation search;
  `plaintext_findings.py` rewritten), `application/secret/plaintext_move.py`,
  `application/sync/round_plaintext*.py`, `domain/sync/plaintext.py`,
  `domain/plaintext_shape.py`, sync and secret HTTP models.
- Packaging: the rule file and licence in `pyproject.toml` package data and
  `backend/coffer-daemon.spec`.
- Contracts: `rule` on secret scan findings, sync plaintext findings and masked
  values (`make contracts`).
- Frontend: Find plaintext keys dialog, Sync page plaintext card, en/zh copy.
- Tooling: `scripts/sync_gitleaks_rules.py`, a Makefile target, the release
  checklist.
- Docs: `docs-site/guides/secrets.md`, `docs-site/guides/vault-sync.md`,
  `docs-site/architecture/vault-sync.md`, `docs-site/architecture/security.md`
  and their `docs-site/zh/` pages.
