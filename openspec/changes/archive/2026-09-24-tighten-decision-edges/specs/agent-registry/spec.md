## MODIFIED Requirements

### Requirement: Switch an agent off with the kind-agnostic enabled flag
An agent MUST carry the kind-agnostic `enabled` flag, toggled through the generic `POST /api/v1/resources/{uid}/enable|disable` routes and `coffer resource enable|disable agent <name>`, and audited as `resource_enabled` / `resource_disabled`. A disabled agent is one Coffer does not write into and does not read from: its delivered skills are reclaimed and nothing new is delivered to it ([skill-manager](../skill-manager/spec.md)), its native memory is not aggregated ([memory](../memory/spec.md)), and its native config does not feed the model catalogue of "Serve each agent type's model catalogue" — the catalogue is read as if no agent of that type were registered. Enabling it again puts back whatever the skills' own state grants, so the switch is never a one-way door. The one exception is adoption ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"): adopting a folder from a disabled agent's skills directory links it in place and records an enabled binding for that agent, the agent's next reconcile reclaims that link and disables the binding, and enabling the agent delivers the skill back whenever the skill's own `enabled` flag and scope grant it. The agent's own routes neither carry nor change the flag: `AgentOut` does not report it and `PATCH /api/v1/agents/{uid}` does not set it.

#### Scenario: disabling an agent reclaims its skills and drops it from the catalogue
- **GIVEN** a registered agent holding a delivered skill, whose config dir the model catalogue reads for its type
- **WHEN** the agent is disabled through the kind-agnostic enabled flag
- **THEN** the delivered skill's link is gone from the agent's skills directory and no binding remains enabled for it
- **AND** the catalogue for that type no longer reads the agent's config dir
- **AND** a `resource_disabled` audit entry names the agent
