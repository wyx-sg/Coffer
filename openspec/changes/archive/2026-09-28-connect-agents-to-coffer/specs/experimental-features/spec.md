## MODIFIED Requirements

### Requirement: Withdraw what a switched-off feature put in front of agents
Switching `memory` off MUST remove the memory delivery hook from every agent it
was installed in, and switching it on MUST install it into every agent connected
to Coffer — every agent carrying Coffer's gateway MCP entry (spec agent-registry
"Connect an agent to Coffer in one action") — and into no other. A daemon that
boots with `memory` off MUST likewise leave no hook in any agent. Switching
`knowledge` off MUST rewrite the `coffer-guide` skill without its knowledge
catalogue, and a channel `/save` MUST answer that knowledge is switched off
without saving; switching it on MUST restore the catalogue. Switching
`vault_sync` off MUST stop every sync attention mark — the web sidebar's and the
desktop shell's — and remove the tray's Sync item. The MCP handshake
instructions and the `coffer-guide` skill MUST name only the tools the tool
list carries: while `knowledge` is off neither names `coffer__write` nor the
knowledge root, and while `memory` is off neither names `coffer__recall`.

#### Scenario: switching memory off removes the delivery hook
- **GIVEN** an agent connected to Coffer with the memory delivery hook installed, and a second agent that is not connected
- **WHEN** `memory` is switched off
- **THEN** the hook is no longer in the connected agent's configuration
- **AND** switching `memory` on installs it again in the connected agent and puts none in the agent that is not connected

#### Scenario: switching knowledge off drops the catalogue from the guide
- **GIVEN** an enabled collection catalogued in `coffer-guide`
- **WHEN** `knowledge` is switched off
- **THEN** the delivered `coffer-guide` carries no knowledge catalogue

#### Scenario: a channel save while knowledge is off saves nothing
- **GIVEN** a paired channel and `knowledge` off
- **WHEN** the owner sends `/save` with text
- **THEN** the reply says knowledge is switched off and nothing reaches any inbox

#### Scenario: agents are told only about the tools they have
- **GIVEN** `knowledge` and `memory` off
- **WHEN** an agent opens a gateway session and reads the delivered `coffer-guide`
- **THEN** neither the handshake instructions nor the guide name `coffer__write` or `coffer__recall`
- **AND** switching `memory` on puts `coffer__recall` back in the guide
