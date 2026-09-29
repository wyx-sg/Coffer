## REMOVED Requirements

### Requirement: Annotate a leftover memory-projection block as safe to delete
**Reason**: Native memory projection was retired long ago and no live feature writes a block into an agent's instructions files, so detecting the old marker and annotating it only keeps a retired mechanism visible in the contract and the editor.
**Migration**: None needed. `ConfigFileContent` no longer carries `memory_block`; a leftover block, if any, is ordinary text the user can edit or delete in the Config files tab like any other.
