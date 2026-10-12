## ADDED Requirements

### Requirement: Keep a Codex memory's id when its bullet moves or is rewritten
A Codex memory's hub id MUST NOT depend on its bullet's position. Its source identity MUST be its file, task group, section and the bullet's content, so inserting, removing or reordering other bullets leaves it unchanged. A bullet whose content identity is not in the hub MUST take over the identity of the most alike entry that the same source published in the same section and that no current bullet holds, when the two are at least 0.6 alike (`difflib` ratio of their descriptions), so a rewritten bullet stays an update; any other bullet MUST be a new memory.

#### Scenario: a Codex memory keeps its id when bullets around it move
- **GIVEN** a published Codex section with three bullets
- **WHEN** Codex inserts a new bullet first, drops the second and swaps the other two, and memory syncs
- **THEN** the two remaining bullets keep their hub ids, the new bullet is created, the dropped one is deleted, and nothing is reported as updated

#### Scenario: a Codex bullet replaced by an unrelated one is a new memory
- **GIVEN** a published Codex bullet
- **WHEN** Codex replaces it with a bullet about something else, and memory syncs
- **THEN** the old hub entry is deleted and the new bullet gets a new id; nothing is reported as updated
