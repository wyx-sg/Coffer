## REMOVED Requirements

### Requirement: Refuse to start on a git older than 2.40
**Reason**: A daemon that refuses to start can only ever be reported as "offline", so the person never learned that git was the cause. The daemon now starts in a setup state that says why and hands the install or update to an agent.
**Migration**: See [daemon](../daemon/spec.md) "Wait in a setup state when git is missing or too old", which keeps the 2.40 minimum and the agent hand-off.
