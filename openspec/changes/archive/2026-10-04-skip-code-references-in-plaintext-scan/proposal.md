## Why

Vault sync's plaintext check refuses to push a file that holds a secret, but it
also refused skill scripts that only read one from somewhere else:
`const token = process.env.SPACE_TOKEN || …` and
`token = args.token or os.environ.get(…)` were each reported as a value, and
the push stopped until the person chose Push anyway. Such a line names where
the secret comes from; it holds none.

## What Changes

- An unquoted value assigned to a secret-sounding name is code, not reported,
  when it is names joined by `.` or `?.` (`process.env.SPACE_TOKEN`,
  `args.token`, `page.next_page_token`), each name made of letters and
  underscores with digits only at its end. A JSON Web Token (`eyJ…`) and a
  dotted value whose parts mix digits in are still values.
- A bare name is code when a declaration (`const`, `let`, `var`, `final`,
  `val`, `auto`) or a member assignment (`self.`, `this.`, `cls.`) gives it.
- `dummy…`, `redacted`, `replace-me…` and `...` join the placeholders that
  are not reported.
- Call, index and list punctuation still marks code; quoted literals and
  `.env`-style values are reported as before; a well-known token shape
  (`ghp_`, `sk-`, `AKIA`, `xoxb-` …) is reported wherever it sits on the line,
  code around it or not.
- The Sync page's `reference` hint uses the same test.

## Impact

- Spec: vault-sync "Refuse to push a plaintext secret" gains the rule and a
  scenario; "Show a plaintext finding in its file" shows its changed-file
  scenario on an example value, since a code reference is no longer a finding.
- Backend: `domain/plaintext_shape.is_reference`, the plaintext scan.
- Docs: the vault-sync guide (en and zh).
