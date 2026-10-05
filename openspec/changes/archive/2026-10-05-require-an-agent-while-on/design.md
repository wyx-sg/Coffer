## Decisions

**Invalid at the domain, not only in the UI.** `validate_scope` rejects an empty
agent list for every kind, so one rule covers the HTTP route, the custom-tool
group, skill adoption and MCP import. The UI keeps the user from building one, and
the backend refuses one that slips through.

**Off keeps the ticks; there is no "off with nothing ticked" to restore.** Because
an empty list is never stored, turning a resource on always restores a reach that
names someone (or everyone). The off callout keeps naming those agents.

**Migrated rows become off + unscoped.** A record with `agents: []` and
`enabled: true` becomes `enabled: false, agents: null`; one already off with `[]`
gets `agents: null`. Unscoped is the only reach left that names no particular
agent. The callout then reads "turning it on gives it to every agent", which is
true. The step lives in `reach_store.py`, runs once from the app lifespan the way
`legacy_cleanup.py` does, is idempotent, and is deleted in a later release
(no load-time shim stays behind).

**The last tick cannot be removed, rather than unticking it switching the
resource off.** Silently flipping the switch from inside the agent list is a
surprise; a disabled checkbox with "turn it off instead" says what to do. Bulk
apply is the exception: there the user is changing many rows at once, and a row
left with nobody is shown as "off" in the preview before it is applied.

**Channel already had a switch.** Its `enabled` flag gates the runtime in
`wanted.py`; dormant was a second gate. Dropping it leaves `_routing`'s check that
the scope admits the default agent, which still applies to a non-empty scope.
