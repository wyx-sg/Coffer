## MODIFIED Requirements

### Requirement: Price usage from a bundled snapshot and per-connection prices
Cost MUST be estimated at ingest, per model and per token category, from a versioned price snapshot
shipped with the release, unless the connection records its own price for that model (relays and
resellers price differently), and stored with the price it used (`snapshot:<version>` or
`override:<connection uid>`) so a later snapshot never rewrites history. A cache category an
override leaves out is charged at its input rate. A model neither prices MUST be marked unpriced,
never costed at zero. The snapshot carries Anthropic's first-party rates only. It carries no OpenAI
(Codex) rates, because Coffer has no verified source for them, and it MUST NOT carry a rate that
is not from the vendor's own published pricing; other vendors' models are unpriced until the user
sets a price on the connection. Every surface labels cost as estimated. Where nothing in a cost is
priced, the web UI and the CLI MUST show `—` in its place, never `$0.00`, and the web UI MUST say
why and where a price is set in the dash's tooltip and accessible name.

#### Scenario: a known model is priced per category
- **GIVEN** a record for `claude-opus-5-5` with input, cache-write, cache-read and output tokens
- **WHEN** it is priced
- **THEN** each category is charged at that model's own rate

#### Scenario: an unknown model is marked unpriced, never zero
- **GIVEN** a record for a model no snapshot or connection prices
- **WHEN** it is priced
- **THEN** it has no cost and is marked unpriced

#### Scenario: stored cost names the price it used
- **GIVEN** one record priced from the snapshot and one from its connection's own price
- **WHEN** both are ingested
- **THEN** each row names the price it was costed with

#### Scenario: a model with no price reads as a dash, never zero
- **GIVEN** usage of a model from a vendor other than Anthropic — a Codex model, or a gateway’s own — through a connection that records no price for it
- **WHEN** the Usage page and `coffer usage` show that model's row
- **THEN** its cost reads `—`, not `$0.00`, with the unpriced request count
- **AND** on the Usage page the dash's tooltip says Coffer ships Anthropic's rates only and a price is set on the connection in Model providers
