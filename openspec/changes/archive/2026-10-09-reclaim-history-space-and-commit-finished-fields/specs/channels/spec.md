## ADDED Requirements

### Requirement: Commit a typed channel setting when its field is finished
On a channel's Settings tab, a value typed into a field (the title, a SeaTalk app id,
the two quiet windows, the idle period) MUST be saved when the person finishes the field,
on blur or Enter, never while they are still typing: a value passed on the way to another
("3" on the way to "32") MUST NOT be saved, so it never takes effect on the running channel
and never becomes a version in the vault. A finished value MUST be saved only when it is
valid and differs from the value last saved; leaving the tab saves a pending one.
Switches, choices and list edits keep saving as they change.

#### Scenario: a value half typed into a channel setting never takes effect
- **GIVEN** a channel whose wait after a text message is 1.5 seconds
- **WHEN** the owner types "3", pauses, types "2" and presses Enter
- **THEN** exactly one save is sent, carrying 32 seconds
- **AND** leaving the field afterwards sends nothing more
