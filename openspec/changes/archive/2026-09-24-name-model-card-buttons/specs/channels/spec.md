## MODIFIED Requirements

### Requirement: Switch the model and reasoning effort from chat
The owner MUST be able to switch the model from chat. `/model` with no argument
reports the current model; `/model <name>` stores the raw upstream model string,
passed through to the bound agent's CLI verbatim. A channel curates no models,
so nothing is validated here: the model namespace belongs to the CLI, not to
Coffer, and a name that agent cannot run surfaces as the CLI's own error relayed
to the chat on the next turn. A model switch takes effect on the next turn in
the same conversation (the model is re-read each turn, unlike the agent and
working directory).

On a transport that `supports_buttons` (see "Offer command choices as
owner-gated selection cards"), `/model` with no argument renders the choices as
a selection card. They come from the agent's model catalogue — read back from
the installed CLI, the one list Coffer has of what that agent can run — in
**full**, because nothing curates it. It is shown one **page** at a time (see "Offer command choices
as owner-gated selection cards"), opening on the page holding the model currently in effect, so a freshly rendered
card always has its tick in view. Free-text `/model <name>` still reaches a
model the user can already name — including one the catalogue does not list —
and the card's body says so. Each button shows the model's **name**, not its raw
id, and the tap still carries the id: a card has no room for the web picker's
name beside the id, and a truncated id can hide the one part that tells two
choices apart. A model with no name shows its id, and a 1M-context variant says
"1M", so `fable` and `claude-fable-5-1[1m]` read as two different choices. No
surface refuses an id: a channel binds an agent and nothing more. With no
suggestions it falls back to the text report.

**`/effort` is the other half of that choice.** For an agent whose models take a
reasoning level, the model id is not the whole decision, and the level is not
part of the model NAME, so it is its own command rather than an argument to
`/model`. It behaves exactly as `/model` does: no argument reports the level in
effect and renders the choices as a selection card where the transport
`supports_buttons`, an argument applies it to the next turn of the SAME
conversation, a tap takes the same path as the text, and Coffer validates
nothing — the level reaches the agent verbatim. The levels offered are those of
the model the conversation is actually ON, read from the same catalogue `/model`
offers, so a level menu never describes a model the conversation is not
running. An agent whose model reports no levels has nothing to choose between:
`/effort` says so in one line rather than rendering an empty card. Like `/model`
there is no clearing form, and `/new` is the way back to the agent's own
default, since a fresh conversation carries no overrides at all.

#### Scenario: /model switches the model for the next turn
- **GIVEN** a paired channel in an active conversation
- **WHEN** the peer sends `/model <name>` and then a message
- **THEN** the next turn runs with the chosen model in the same conversation

#### Scenario: a model card button shows the model's name
- **GIVEN** an agent whose catalogue offers `fable`, named "Fable 5.1", and
  `claude-fable-5-1[1m]`, named "Fable"
- **WHEN** the `/model` card is built
- **THEN** the buttons read "Fable 5.1" and "Fable 1M"
- **AND** tapping either carries its model id
