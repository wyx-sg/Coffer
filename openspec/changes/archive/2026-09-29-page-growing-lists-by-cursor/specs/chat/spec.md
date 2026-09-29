## MODIFIED Requirements

### Requirement: List conversations by latest activity
Conversations MUST list newest-activity first, and a conversation's activity
timestamp MUST be bumped both when a turn **starts** and when it **finalises**
— a long turn moves its conversation to the top of the list when it begins, and
is still ordered correctly when it ends. Active and archived are two listings,
never one list with a flag every caller must remember. Both listings MUST page
by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor")
with the conversation id as the tie-break, so a conversation whose activity is
bumped while a reader pages moves to the head rather than appearing twice.

#### Scenario: the conversation list is ordered by activity, not by creation
- **GIVEN** two conversations created in order,
- **WHEN** a turn starts on the older one and then completes,
- **THEN** it heads the active listing both while the turn runs and after it
  ends.

#### Scenario: the conversation list pages by cursor
- **GIVEN** three active conversations
- **WHEN** the active listing is read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the two with the latest activity and the second the third, with a `null` `next_cursor`
