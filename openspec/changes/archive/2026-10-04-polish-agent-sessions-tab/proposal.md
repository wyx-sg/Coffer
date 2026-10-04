## Why

The agent detail page's Sessions tab was hard to scan and showed raw attachment placeholders as titles.

## What Changes

- A transcript's turns are set apart by who spoke: the person's turns are right-aligned accent bubbles like the Chat page's, the agent's replies stay unboxed on the left under its mark.
- The divider between the session list and the reader is draggable, with the width remembered per browser.
- The Project filter has a search box matching the full project path.
- Attachment placeholders such as `[Image: source: /path]` and `[Image #1]` are stripped from session titles; a turn that is nothing but placeholders is not a title candidate. The transcript summary sidecar carries a format version so titles derived by older parsers are re-derived.

## Capabilities

### Modified Capabilities

- `agent-registry`: "Lead a transcript turn with the person's own words" gains the set-apart rule; "List an agent's transcript sessions read-only" gains the attachment-marker rule.

## Impact

Frontend `AgentTranscriptView`, `AgentSessionsTab`, `ProjectPill`; backend `transcript_parsers` and `transcript_cache`; the Agents guide (en and zh).
