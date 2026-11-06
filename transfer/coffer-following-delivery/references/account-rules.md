# Account Developer boundaries

Profile: shopee-account. Jira is the phase authority; DW is an executor. Both belong to the exact allowlisted ticket and verified Developer. Workdays are Monday-Friday 10:00 <= Asia/Singapore time < 19:00, excluding MOM public/observed holidays. Missing annual coverage blocks new business actions (the script enforces the window and calendar).

| Situation | Developer action and completion evidence |
| --- | --- |
| Waiting/Doing | Read PRD/TD and dependencies; reuse/create Jira-linked DW Project. Separate implementation, independent auxiliary review and self-tests, tied to actual MR/head SHA. DW completed alone is insufficient. |
| Review returned to Doing | Read actual status history and MR feedback; repair the same task/MR and return to the original review round. Do not restart unrelated development. |
| External Integration | Merge test directly, prepare required config/resources and deploy default Test for integration. |
| Before Testing/UAT | Preserve human review/acceptance gates. Direct environment merge, no environment MR; config/deploy/developer verification precede entering the phase via real legal transitions. |
| Testing/UAT | Fix developer defects and support environment; do not sign for QA/PJ/PM or advance phase merely because deployment succeeded. |
| Staging preparation | Prepare/publish Staging config/resources; submit the ticket into the precise Release Engine release cycle/version and read back its scope before asking the human Reviewer to merge the development MR into main. Track existing automatic Staging pipeline; do not merge/deploy Staging a second time. |
| Live preparation | Prepare config diff, release steps, dependencies, rollback and verification. This standing workflow does not grant broad Live mutation authority. |
| Emergency | Prepare SWP and submit the SWP ticket to the correct emergency Release Engine flow; preserve approvals. Human Reviewer merges release, which deploys immediately. Missing submission/ACK contract blocks the action. |

Prefer default Test, with PFB only for a concrete incompatibility requiring it. Preserve middleware/config/schema rollout ordering, exact environments/regions and candidate versions. Read Jira transitions at action time; global status order does not establish a legal direct transition.

RE membership means an actual Release Engine scope submission/readback, not editing a Jira field. Reviewer review/merge, QA tests and PJ/PM acceptance stay with their owners. Work already in progress can finish necessary reconciliation after 19:00; new business actions wait for the next permitted window.
