## REMOVED Requirements

### Requirement: Show Coffer's own background work beside the owner's tasks
**Reason**: The owner wants the Scheduled tasks page to hold only their own tasks; the daemon's workers read as tasks there.
**Migration**: `coffer daemon status --workers` still lists the wakeable workers.
