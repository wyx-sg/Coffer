## 1. Rule import

- [ ] 1.1 `scripts/sync_gitleaks_rules.py`: download `config/gitleaks.toml` and `LICENSE` at the pinned release (default v8.30.1, `--version` to override), resolve its commit, translate every pattern (design D1), write `backend/coffer/infrastructure/secret/rules/gitleaks.toml` with the source / release / commit / licence / untranslatable-rules header and `gitleaks.LICENSE` beside it; exit 1 on an untranslatable rule; `--check` exits 1 when the files would change
- [ ] 1.2 Run it for v8.30.1 and commit the generated files
- [ ] 1.3 Ship the rule directory: `pyproject.toml` package data, `backend/coffer-daemon.spec` datas; `scripts/check_pyinstaller_specs.py` passes
- [ ] 1.4 `make refresh-secret-rules` (and its help line)
- [ ] 1.5 Translation tests on fixed rule fragments, offline: mid-pattern flag groups across `|`, `\z`, `$`, POSIX classes, ASCII classes, an untranslatable construct reported, header contents

## 2. Executor

- [ ] 2.1 Rule loading (once per process) and the executor with gitleaks semantics (design D2): secret group, entropy, keywords, path condition, global and rule allowlists with regex targets, stopwords, paths and `AND`; findings as `(rule, start, end)` text offsets with line / column helpers; one finding per value
- [ ] 2.2 Keyword-window scanning (design D3)
- [ ] 2.3 Coffer allowlist and `coffer-password-assignment`, `coffer-url-password`, `coffer-server-setting` (design D4)
- [ ] 2.4 Per-rule tests: a generated positive and a shortened negative for every imported rule, hand-assembled samples for the rules the generator cannot build, and a test that fails for any rule without a sample
- [ ] 2.5 Tests for Coffer's allowlist and rules, for multi-rule de-duplication, and that a 1 MB single-line blob scans in bounded time
- [ ] 2.6 Acceptance tests: `acceptance("secret", "a vendor token is found and named by its rule")`, `acceptance("secret", "a secret reference is not a finding though it looks like a key")`, `acceptance("secret", "a weak password and a password in a URL are found")`, `acceptance("secret", "the bundled rules say where they came from")`

## 3. Callers

- [ ] 3.1 Find plaintext keys: `plaintext_findings.scan_skills` / `scan_server` on the executor; `Finding.rule`; `Hit` offsets in the file so `rewrite_file` replaces a multi-line value whole
- [ ] 3.2 Push check: `round_plaintext.findings` and `sync_wiring` on the executor; `PlaintextFinding.rule` (default empty for rounds recorded before)
- [ ] 3.3 Masked context: `mask_line` replaced by masking from executor findings; `MaskedValue.rule`
- [ ] 3.4 Delete `line_hits`, `find_in_text`, `SECRET_KEY`, `TOKEN_SHAPES`, `_ASSIGNMENT` and the old server patterns; `plaintext_scan.py` keeps only the citation search; update the integration harnesses that injected `find_in_text`
- [ ] 3.5 HTTP models + `make contracts`; frontend shows the rule in the Find plaintext keys dialog, the Sync plaintext card and the masked context; en/zh copy
- [ ] 3.6 Acceptance tests: `acceptance("secret", "a private key in a skill moves into the store whole")`, `acceptance("vault-sync", "a vendor token in a knowledge note stops the round")`, `acceptance("vault-sync", "a resource document's secret references do not stop a push")`; update the existing plaintext tests to the new rules and fixtures

## 4. Rule refresh

- [ ] 4.1 Add `make refresh-secret-rules` next to `make refresh-prices` in `RELEASING.md`, `docs-site/contributing/development.md` (+ zh) and `.agents/harness.md` (design D7)

## 5. Docs

- [ ] 5.1 `docs-site/guides/secrets.md`, `docs-site/guides/vault-sync.md`, `docs-site/architecture/vault-sync.md`, `docs-site/architecture/security.md` and their `docs-site/zh/` pages: what the detection covers, the rule names shown, where the rules come from and how they are refreshed
- [ ] 5.2 Third-party notice for the gitleaks rules wherever the price list's notice is listed

## 6. Finish

- [ ] 6.1 `make -C . verify`
- [ ] 6.2 `npx openspec archive detect-plaintext-with-gitleaks-rules --yes` in the same PR
