## ADDED Requirements

### Requirement: Remember a value a person says is not a secret
A person SHALL be able to say a plaintext finding is not a secret, and Coffer MUST then stop
reporting that value on this machine: in **Find plaintext keys** (see "Move plaintext secrets in
managed resources into the store") and in vault sync's check before a push
([vault-sync](../vault-sync/spec.md) "Refuse to push a plaintext secret"), wherever the value
sits and whatever else in its file changes. A different value in the same place is reported.

Coffer MUST remember the value by a fingerprint only: an HMAC of the value under a key derived
from the master key, so the list holds no value and no plain hash a guess could be checked
against. The list is machine-local state and is never synced; each entry keeps the place, rule
and key it was first found at, who said so and when.

`POST /api/v1/secrets/scan` MUST mark each finding whose value is remembered as `ignored`.
`POST /api/v1/secrets/scan/ignore` and `POST /api/v1/secrets/scan/unignore` (the finding ids)
MUST remember and forget the chosen findings' values, each audited as
`secret_plaintext_ignored` or `secret_plaintext_unignored` naming the places and rules, never a
value. `coffer secret ignore` and `coffer secret unignore` do the same. When the master
key is not available no fingerprint can be made, and the request MUST be refused with
`SECRET_LOCKED` (503).

The Find plaintext keys dialog offers **Not a secret** on each finding, which remembers it and
takes it off the list, and **Show ignored (N)**, which lists the remembered findings with
**Report again** on each. Remembered findings are never ticked for moving.

#### Scenario: a finding marked not a secret is not reported again
- **GIVEN** a skill file whose line holds a value the scan reports
- **WHEN** the finding is marked not a secret, another line of the file is edited, and the scan runs again
- **THEN** the finding comes back marked `ignored`, one `secret_plaintext_ignored` entry names its place and rule without the value, and the remembered list holds no copy of the value
- **AND** after the value itself is changed the scan reports it as not ignored

#### Scenario: a remembered value can be reported again
- **GIVEN** a finding marked not a secret
- **WHEN** it is unignored and the scan runs
- **THEN** it is reported as not ignored, and `secret_plaintext_unignored` is recorded

#### Scenario: the dialog hides what is not a secret
- **GIVEN** the Find plaintext keys dialog with two findings
- **WHEN** Not a secret is chosen on one
- **THEN** it leaves the list, Show ignored (1) lists it with Report again, and Review changes moves only the other
