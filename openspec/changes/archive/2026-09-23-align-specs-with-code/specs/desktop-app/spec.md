## MODIFIED Requirements

### Requirement: Consume the one frontend build the daemon serves
The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (see "Supply the page its daemon connection over IPC") and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting. Two host-conditional affordances are sanctioned, both rendered in the offline banner and both reached through the credential supplier's module, because only the shell can offer them: the Restart control, and the version-skew check that warns when the shell has reached a daemon from an earlier app version (see "Find or start a daemon by a fixed resolution order"). Outside the shell the skew check always answers "matches", since a browser is served by whichever daemon is running and has no pairing to be out of step with.

#### Scenario: the shell hosts the one build the daemon serves
- **GIVEN** the shell's bundle configuration and the daemon's frozen-build recipe,
- **WHEN** each names the web UI it ships,
- **THEN** both name the repository's `frontend/dist`, produced by the frontend's single `npm run build`,
- **AND** outside the credential supplier and the offline banner — which carries the Restart control and the version-skew warning — no frontend module branches on whether it is running inside the shell.
