## MODIFIED Requirements

### Requirement: Introspect the endpoint when the Models tab opens
A connection's Models section MUST introspect the endpoint when the connection opens, once per visit, without a user action, and
MUST show that it is doing so; there is no "Fetch models" button, because making the user press one
made "the endpoint offers nothing" and "nothing asked it" indistinguishable. A probe that FAILS MUST
say so on the surface — in the section's title ("Listing failed · last listed <date>") and in a box naming what failed — and leave **Refresh**, which sits in the section's title, as the one way to try again; the box carries no Retry of its own, and the failure shows only in the Models section, not on the Used by rows. It MUST NOT fail silently. A failed or empty probe MUST
leave the curated `models` selection unchanged, and the empty-means-unrestricted semantics (see
"Curate the models a connection offers") MUST be unaffected.

The section lists one row per model id — its switch (offered or not), id, what uses it, its price and its type — with a search and a Type filter. The one sentence under the section title says where prices come from once ("bundled with Coffer, updated <date>", or from the provider), so a row marks only the exception: **You set**, **Set price…** or **Local · no cost**. The type is a five-value select, shown as plain text with a chevron that opens its menu, pre-filled from what introspection guessed and
correctable in place; a correction on an already-offered row patches the curated set immediately,
while one made on a row not offered yet is held on the surface and travels into the entry when its
switch is turned on.

#### Scenario: the models table lists the endpoint's models when it opens
- **GIVEN** a connection whose endpoint serves a model list,
- **WHEN** the connection's detail is opened,
- **THEN** the endpoint is introspected without any user action and its model ids fill the table, each with its own offered/not-offered switch — there is no "Fetch models" button.
#### Scenario: a failed model introspection says so, with Refresh in the title
- **GIVEN** a connection whose endpoint refuses the model-list probe,
- **WHEN** the connection is opened,
- **THEN** the Models section's title reads "Listing failed" with Refresh beside it and a box says the endpoint's models could not be listed, with no Retry in the box, and the connection's existing curated selection is left exactly as it was.
