## MODIFIED Requirements

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)),
and MUST expose one kind-agnostic REST surface, `/api/v1/resources*`, to list, read, update,
enable, disable and delete any of them without the caller knowing the kind. Every route and
every stored reference from one resource to another MUST address the uid. A uid MUST be minted
once and never reused, and MUST be the same value on every machine that holds the resource, so
that two machines can tell "the same thing" from "a different thing with the same name" without
asking each other.

The lifecycle controls of the web UI are exactly these routes: list, read, update — the
description, `title` on a kind that carries one ("Carry an optional editable title on the kinds that
have one"), and the kind's own fields — enable, disable and delete, plus the reach pair ("Carry a
per-agent reach on every resource"). Creating is not one of them: a kind registers through its own
seam (see "Keep creation a per-kind seam"). A request a kind does not support MUST be refused rather
than ignored (see "Keep creation a per-kind seam" and "Carry a per-agent reach on every resource").

A kind MAY declare that its resources cannot be disabled — `knowledge`, `memory` and `agent` do.
Every resource of such a kind MUST read as enabled, whatever its stored reach holds (a resource disabled before its kind became non-toggleable reads enabled from then on), and enabling or disabling one through the
kind-agnostic surface MUST be refused with `RESOURCE_NOT_TOGGLEABLE` (409), changing
nothing. The resource read carries the kind's answer as `toggleable`, so a surface can
leave the switch out rather than offer one that is refused.

A kind exists only because the composition root registered it; a request naming an
unregistered kind MUST be refused rather than bringing one into being.

#### Scenario: the kind-agnostic surface serves every kind
- **GIVEN** resources of more than one registered kind exist,
- **WHEN** the user lists resources without naming a kind, reads one back by its uid, then disables and re-enables it,
- **THEN** every kind's resources appear in the one list, each carrying its uid, kind, name, title, config, reach and enabled flag,
- **AND** the enable/disable round trip is served by the same route for every kind, and each step is audited.

#### Scenario: every kind answers the same lifecycle routes
- **GIVEN** one registered kind that can be disabled, supports reach and carries a title, and one that does none of these
- **WHEN** each resource is read with `GET /api/v1/resources/{uid}`, given a new description with `PATCH /api/v1/resources/{uid}`, and sent a non-null scope with `PUT /api/v1/resources/{uid}/scope`, a title and `POST /api/v1/resources/{uid}/disable`
- **THEN** both kinds answer the read and the description update through the same routes, and the kind that supports no reach, carries no title or cannot be disabled refuses that request and changes nothing
- **AND** the first kind's disable changes it through the kind-agnostic route and is audited

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection, a `memory` partition and an `agent`
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** all three requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** all three still read back enabled, with `toggleable` false
- **AND** an agent whose stored reach says off, left from before the kind was non-toggleable, reads back enabled
