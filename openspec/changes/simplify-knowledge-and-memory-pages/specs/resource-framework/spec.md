## MODIFIED Requirements

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)),
and MUST expose one kind-agnostic surface — `/api/v1/resources*` and `coffer resource` —
to list, read, update, enable, disable and delete any of them without the caller knowing
the kind. Every route and every stored reference from one resource to another MUST
address the uid. A uid MUST be minted once and never reused, and MUST be the same value
on every machine that holds the resource, so that two machines can tell "the same thing"
from "a different thing with the same name" without asking each other.

A kind MAY declare that its resources cannot be disabled — `knowledge` and `memory` do.
Every resource of such a kind MUST be enabled, and enabling or disabling one through the
kind-agnostic surface MUST be refused with `RESOURCE_NOT_TOGGLEABLE` (409), changing
nothing. The resource read carries the kind's answer as `toggleable`, so a surface can
leave the switch out rather than offer one that is refused.

A kind exists only because the composition root registered it; a request naming an
unregistered kind MUST be refused rather than bringing one into being.

#### Scenario: the kind-agnostic surface serves every kind
- **GIVEN** resources of more than one registered kind exist,
- **WHEN** the user lists resources without naming a kind, reads one back by its uid, then disables and re-enables it,
- **THEN** every kind's resources appear in the one list, each carrying its uid, kind, name, config, reach and enabled flag,
- **AND** the enable/disable round trip is served by the same route for every kind, and each step is audited.

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection and a `memory` partition
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** both requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** both still read back enabled, with `toggleable` false
