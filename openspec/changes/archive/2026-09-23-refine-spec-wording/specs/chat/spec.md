## MODIFIED Requirements

### Requirement: Offer models from a fixed dropdown that keeps the current value
The model picker MUST be a fixed dropdown, never free text. It MUST always lead
with a **Default** option, which clears the conversation's model so the agent
runs its projected default and is what the picker shows while no model is set.
After it come the models the platform offers for the agent
([provider-switching](../provider-switching/spec.md) "Serve one model list to
every surface": the agent's own catalogue, or the active connection's curated
`text` ids when one is active — an active connection that curates models, none
of them `text`, offers none) and the **current value** — which MUST stay
selectable whatever that list contains, so a conversation never shows a picker
that cannot represent the model it is actually on. Those are the only options:
the page does not introspect a connection's endpoint itself.

#### Scenario: the model picker always offers the current value
- **GIVEN** a conversation set to a model the agent's catalogue does not list,
- **WHEN** the model picker is opened,
- **THEN** the current value is among the options and is selected, and the
  picker accepts no free text
- **AND** the Default option is offered first, alongside the catalogue's models.
