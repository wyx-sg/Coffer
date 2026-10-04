## ADDED Requirements

### Requirement: Show the commands Coffer itself runs on the CLIs page
The CLIs page MUST list the commands Coffer runs itself (spec skill-manager
"List the commands Coffer itself runs") like any other CLI, counting Coffer
among who needs one — "Coffer", or "Coffer and 1 skill" when a skill needs it
too. The detail's Needed by MUST show a Coffer row first, of kind Coffer, naming
its uses (Vault history · Sync) and opening nothing, and the banner of a missing
or outdated one MUST say what Coffer can't do without it ("Coffer can't keep the
vault's history and sync the vault.").

#### Scenario: git shows Coffer under Needed by
- **GIVEN** `git` needed by Coffer alone and missing on this machine
- **WHEN** the user opens `/clis/git`
- **THEN** the list row reads "Not found · Coffer needs it", the banner says Coffer can't keep the vault's history and sync the vault, and Needed by shows one Coffer row naming Vault history · Sync
