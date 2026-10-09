## ADDED Requirements

### Requirement: Name the model the default resolves to
Every place a channel shows its no-override model choice — `Default model` in the `/model` card and its text fallback, the reply to `/model default`, the settings line of `/status` and `/new`, and Provider default in the channel's Overview › Agents — MUST name the model it resolves to when Coffer can know it, as `Default model (<name>)` (`Provider default (<name>)` on the web), and MUST name none otherwise. The model is the agent's resolved default from [provider-switching](../provider-switching/spec.md) "Name the model a default resolves to", shown by the name its `/model` card button carries.

#### Scenario: the default model names the model it resolves to
- **GIVEN** a channel on an agent whose default resolves to `gpt-5-codex`, labelled `GPT-5 Codex`
- **WHEN** the owner sends `/model default` and then bare `/model`
- **THEN** the reply reads `Model: Default model (GPT-5 Codex) — from your next message` and the model text names `Default model (GPT-5 Codex)`
- **AND** for an agent whose default Coffer cannot know, the same replies read plain `Default model`
