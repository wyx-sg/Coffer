## MODIFIED Requirements

### Requirement: Converge resource definitions as serialized documents
`mcp_server`, `agent`, `skill`, `knowledge`, `provider` and `channel`
definitions MUST converge, serialized to text from SQLite, which stays the
system of record. A resource document is identity, title, description and
config — what the resource *is*. What it reaches is not in it (see "Keep reach
machine-local").

The `title` is optional in the document. A resource with no title MUST be
serialized without the key, and a document that carries no `title` MUST leave
the receiving machine's title empty, so a machine running an older version,
which writes no `title`, and a newer one converge on the same resource. Setting,
changing or clearing a title on one machine MUST reach every other machine as a
modification of that one document. A kind that carries no title (`agent`,
`mcp_server`, `skill` — [resource-framework](../resource-framework/spec.md) "Carry
an optional editable title on the kinds that have one") MUST apply a document
that still carries one, from an older build, with the title ignored rather than
refuse it.

#### Scenario: a resource document is identity, description and config
- **GIVEN** a registered resource with a description, a config and a reach of its own
- **WHEN** it is serialized into a resource document
- **THEN** the document holds its identity, its description and its config
- **AND** it holds nothing else — no `enabled` flag and no `scope`

#### Scenario: a resource document carries the title when there is one
- **GIVEN** a registered resource with a title, a description, a config and a reach of its own
- **WHEN** it is serialized into a resource document
- **THEN** the document holds its identity, its title, its description and its config
- **AND** it holds no `enabled` flag and no `scope`

#### Scenario: a title set on one machine converges to the other
- **GIVEN** a resource that two converged machines hold, with no title on either
- **WHEN** the user sets its title on one machine and the two converge
- **THEN** the other machine shows the same title for the same resource
- **AND** clearing the title on either machine and converging again leaves it empty on both

#### Scenario: a document without a title leaves the title empty
- **GIVEN** a resource document that carries no `title` key
- **WHEN** a machine applies it
- **THEN** the resource is registered or updated with an empty title and every other field the document carries

#### Scenario: a title on a kind without one is ignored on apply
- **GIVEN** a document for an MCP server that carries a `title` key, written by an older build
- **WHEN** a machine applies it
- **THEN** the server is registered or updated from the document with no title, and the round reports no failure for it
