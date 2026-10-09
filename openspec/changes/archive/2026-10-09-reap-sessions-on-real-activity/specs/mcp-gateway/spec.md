## MODIFIED Requirements

### Requirement: Take the agent identity from the handshake
The system MUST accept a self-reported agent identity at MCP handshake as the agent's **uid**
(`params._meta["coffer/agent-uid"]`, alongside the existing `coffer/cwd` key), written into a managed agent's
shim invocation as `coffer-mcp-shim --agent-uid <uid>` by the Coffer-MCP install ([agent-registry](../agent-registry/spec.md) "Install Coffer's MCP server into an agent in one action") —
the uid rather than the name, because the entry is written once into a file Coffer does not revisit and a name
goes stale on the first rename. A session's reported identity is carried for the life of that connection and
used for every subsequent list and call.

- A session id the daemon does not know — its idle session was dropped, or the daemon restarted — MUST be
  answered `404` for every method but `initialize` (and for a notification stream), never silently rebuilt as
  a session that lost the handshake's identity and scope; the shim MUST then replay its cached `initialize` and
  resend the call. A session id that starts with `__` MUST NOT be taken as a client's session id. An open
  notification stream is not activity: a session is idle when it has seen no downstream request and no forwarded
  upstream notification for 10 minutes (`COFFER_MCP_SESSION_IDLE_S` changes the window), a request in flight keeps it
  alive, and the keepalive wake-ups of an open stream do not. Reaping a session ends its open stream cleanly, and
  the client's next request on that id is answered `404`.
- The handshake happens once per session: a second `initialize` on a session that already completed one MUST
  be refused with JSON-RPC `-32600` and change nothing — not the identity, the client's capabilities or the
  cwd. A new session may report any identity, as before.
- A `_meta` carrying only a name-based `coffer/agent` key MUST be treated as reporting no identity rather than
  resolved by name.
- A session with no reported identity (a hand-configured shim invocation, or any client that omits
  `--agent-uid`) MUST be treated as `agent=None`, matching only servers that carry no scope — never a scoped
  one, even one naming the agent that happens to be running unidentified. An unidentified session sees
  strictly less, never more.
- Identity is self-reported, not cryptographically verified — a documented trust boundary, acceptable under
  the loopback-only, single-user posture [daemon](../daemon/spec.md) holds: any local process able to open the
  loopback MCP connection and set `_meta` could claim any agent uid.
- Identity is reported **once, at the handshake**, and nowhere else: when the gateway threads the identity
  into a Coffer built-in tool call (as an `agent` argument), it
  MUST overwrite any `agent` the client put in the call's arguments with the session's, and MUST drop the
  argument entirely when the session reported none — so a client cannot pick a different identity per call,
  and no built-in tool advertises `agent` in its input schema.

#### Scenario: a dropped session is answered 404 and the client handshakes again
- **GIVEN** a session whose handshake reported an agent's uid and that the idle reaper has since dropped,
- **WHEN** the client sends `tools/list` on its old session id,
- **THEN** the answer is `404` and no session is created; an `initialize` carrying the identity then opens a new one, and the shim does both and resends the call

#### Scenario: an open notification stream with no requests does not keep a session alive
- **GIVEN** a session whose client holds its notification stream open and sends no request,
- **WHEN** the session has been idle past the idle window,
- **THEN** the reaper drops it and its stream ends cleanly,
- **AND** the client's next request on that session id is answered `404`

#### Scenario: a name-only handshake is treated as unidentified
- **GIVEN** one server scoped to a single agent's uid and one unscoped server,
- **WHEN** a session's handshake `_meta` carries only a `coffer/agent` key naming that agent, and no `coffer/agent-uid`,
- **THEN** the session reports no identity,
- **AND** its `tools/list` shows only the unscoped server's tools.

#### Scenario: a built-in tool call carries the session's identity, not the client's
- **GIVEN** a session whose handshake reported a registered agent's uid, and a second session that reported none,
- **WHEN** each calls a Coffer built-in tool with an `agent` argument naming a different agent,
- **THEN** the identified session's call reaches the tool with its own agent in `agent`, and the unidentified session's call reaches it with no `agent` argument at all,
- **AND** no built-in tool Coffer advertises in `tools/list` declares `agent` in its input schema.

#### Scenario: a second initialize on a session changes nothing
- **GIVEN** a server scoped to agent `A`, and a session whose handshake reported agent `B` and whose call to that server was refused
- **WHEN** the same session sends `initialize` again reporting `A`
- **THEN** that `initialize` is answered `-32600`, the next call is still refused as out of scope with no upstream request, and a new session reporting `A` may call the server
