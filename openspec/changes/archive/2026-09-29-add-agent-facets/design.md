## Context

The ADR records the options and the decision; this is how it lands.

## Decisions

- **Ports belong to the kind that consumes them.** The descriptor names each
  facet's type; where a kind consumes a facet, the type is that kind's own
  Protocol (the memory kind's reader and delivery hook, the chat kind's driver,
  the provider kind's translation), named from the agent domain for annotation
  only. The dependency probe and the projection registry are the agent kind's.
- **Implementations declare their agent.** Every facet implementation says
  which agent it serves (by the agent type's value where its kind may not
  import the agent kind). The binder groups by that declaration, so the
  composition root lists implementations and never says which is which, and
  a second implementation for one agent is refused at startup.
- **The pure table stays pure.** The descriptor table carries no mechanism; the
  composition root builds a bound catalogue and hands it to every consumer.
  Tests build the same catalogue with a fixed-answer probe.
- **Provider plans, not writes.** A provider facet returns the main file's new
  text plus files written before it and removed after it, so the catalogue
  file Codex points at is always there when the pointer is. The presence check
  is the facet's too, so the boot heal cannot drift from what projection writes
  (Codex's shell-environment exclude entry alone is not a projection).
- **Revert by agent type.** `is_active` is one flag per connection and the
  single-active rule is per agent type, so the revert names an agent type and
  switches the connection covering it off as a unit.
- **The probe is generic.** One probe per agent, built from the descriptor's
  program name: the user's login-shell `PATH` (asked once per process, through
  the platform package) merged with the inherited one, `--version` with a
  five-second bound, the answer cached per binary file. `--version` needs no
  login and reads no config.
- **Candidates are per directory.** The standard directory and the one the
  agent's own environment variable names in the daemon's environment are the
  only directories looked at. A registered directory is not offered again; a
  custom registration no longer hides the standard directory, which is a config
  set of its own.
- **Hooks are read, not managed.** The reader parses the one JSON shape both
  agents use, from the descriptor's hook-carrying files and each enabled
  plugin's hook file. Project-level files are not read: Coffer does not know
  which repositories the agent is used in.
- **The gate reads syntax.** It fails on a named `AgentType` member or a
  comparison with an agent type's literal value outside the descriptor, the
  agent kind's infrastructure, the listed facet implementations and the
  migrations.
