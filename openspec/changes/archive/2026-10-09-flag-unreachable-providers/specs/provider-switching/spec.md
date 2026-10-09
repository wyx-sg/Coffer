## ADDED Requirements

### Requirement: Know each connection's health without opening it
The daemon MUST keep one health verdict per connection — `reachable`,
`key_rejected` or `unreachable` — with when it was made, when that status was
first seen (`since`), whether it came from a `check` or an agent's `request`,
and, for a failure, why (cut to 200 characters). A verdict is an observation
this machine can make again and lives in `derived.db`, keyed by the
connection's uid; a deleted connection's verdict is forgotten. It MUST be
written by:

- a **check** — the same model listing the detail page makes, which spends no
  token: every enabled connection at boot and every 30 minutes, a connection
  again once its resource is written (a replaced key or a corrected URL clears
  its error without waiting), the detail page's own probe when it names the
  connection (`connection_uid` on `POST /api/v1/models/list-models`, honoured
  only when the call carries that connection's own stored key, URL and wire),
  and `POST /api/v1/providers/{uid}/check`;
- a **request** — what the local model proxy saw relaying an agent's real
  call, read from its usage records: a 401 or 403 is `key_rejected`, a
  connection that never opened (`connect_error`) is `unreachable`, a completed
  2xx answer is `reachable`. Any other outcome (a 429, a 5xx, a cut stream, a
  cancel) changes nothing.

A listing that fails with 401/403 or names an invalid or unauthorised key is
`key_rejected`; any other failure is `unreachable`; an endpoint that answers
with no models is `reachable`. A verdict older than the kept one MUST be
dropped. A check MUST NOT send a stored key whose destination waits for
approval or was refused: that connection is skipped. `GET
/api/v1/providers/health` MUST answer every kept verdict without calling any
endpoint. All of it follows the `models` feature. A moved status is announced
on the event stream as a `provider` change, and the attention list is
recomputed.

The provider list MUST mark every row whose verdict is `key_rejected` or
`unreachable`: its sub-line reads the status (Key rejected, Unreachable) in
the error colour in place of protocol and models, whether or not the row is
open. The open row follows its own live probe.

#### Scenario: a connection that never opened is marked in the list
- **GIVEN** two connections, one whose endpoint refuses its key and one that answers, neither opened
- **WHEN** the daemon's sweep has listed both and the provider list renders
- **THEN** `GET /api/v1/providers/health` reports `key_rejected` and `reachable`, and the first row reads "Key rejected" in red while the second reads its protocol and models (TypeScript acceptance test)

#### Scenario: an agent's refused request marks its connection
- **GIVEN** a connection the last check found reachable
- **WHEN** the proxy records an agent's request to it answered with HTTP 401
- **THEN** its verdict becomes `key_rejected` from a `request`, and a usage record older than that verdict does not change it back

#### Scenario: a replaced key is checked again at once
- **GIVEN** a connection whose verdict is `key_rejected`
- **WHEN** the user replaces its key and the endpoint now lists models
- **THEN** the connection is checked again without waiting for the sweep and its verdict becomes `reachable`

#### Scenario: a key waiting for approval is not sent by a check
- **GIVEN** a connection whose key waits for approval to a new base URL
- **WHEN** the sweep runs
- **THEN** that connection's endpoint is not called and its verdict is unchanged

#### Scenario: a listing made with a typed key says nothing about the saved connection
- **GIVEN** a saved connection with a kept verdict
- **WHEN** the Edit dialog lists models with a typed, unsaved key and the connection's uid
- **THEN** the kept verdict is unchanged
