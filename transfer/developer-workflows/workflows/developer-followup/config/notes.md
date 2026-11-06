# Developer follow-up — project notes

Read on every `work` run of `coffer-following-delivery`.

- Scope: only the allowlisted tickets in `followup.json` whose current Jira Developer is the configured identity. Never act for Reviewer, QA, PJ or PM.
- SPB-71683 and SPB-71414 are related: check their DW Project and branch owner before starting work on either; one implementation owner for a shared branch.
- Do not start work on a repo or branch owned by another current writer or an unrelated agent chat.
- Deployment and config publication have no continuous observer yet: read them back through their domain skill and do not claim they are watched.
- Human-readable reports go under `reports/developer-followup/`, receipts under `receipts/developer-followup/` (paths relative to the developer-workflows root).
