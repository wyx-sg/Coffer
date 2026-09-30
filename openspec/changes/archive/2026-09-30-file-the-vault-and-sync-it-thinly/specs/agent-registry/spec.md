## MODIFIED Requirements

### Requirement: Keep the transcript summary sidecar disposable
The listing MAY keep a **disposable derived sidecar** of those summaries so a cold parse is not repeated on every daemon restart — an agent's transcripts run to thousands of files and gigabytes, and re-deriving them is seconds of blocking I/O. The sidecar holds no message text, lives **in the derived class, outside the vault and every database** — under `~/.coffer/derived/cache/agent/` — at one path the user may delete at any moment, and no export or backup carries it. It MUST never change an answer, only the time to reach one: a summary is served from it only while its file's modification time and size still match, and with the sidecar missing, empty, corrupt or mid-write the listing MUST still be correct — merely slower. The system MAY warm it in the background, off the request path, so the first visit after an install is not the one that pays. Everything the listing returns is still derived from the agent's own files on disk: nothing about a session is a stored truth. Like the other workspace listings, neither the listing nor the warm pass emits an audit event.

#### Scenario: list transcripts correctly with an unusable sidecar
- **GIVEN** an agent with transcript sessions on disk and a summary sidecar that is corrupt
- **WHEN** the transcripts are listed
- **THEN** the listing returns the same sessions it returns with no sidecar at all

## REMOVED Requirements

### Requirement: Drop nothing locally when the plugin inventory document is deleted
**Reason**: The plugin inventory is no longer a sync state document: each machine records its agents' plugins in its own machine descriptor, which only that machine writes, so there is no inventory document another machine could delete.
**Migration**: [vault-sync](../vault-sync/spec.md) "Record plugins as an inventory, not a replicator".
