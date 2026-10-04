## Why

The System canvas (6.1 Secrets) lands two signals from the secret kind on the
Overview's "needs you" list — secrets with no value on this Mac and changes
waiting for approval — and drops the refused-approvals feature: a refusal is the
person's own click, so the Secrets page no longer lists refused changes or
offers "Ask again".

## What Changes

- The secret kind contributes two attention items, each one item for a *set*:
  `secret_missing_here` (error, action `open` → Secrets page) and
  `secret_approvals_pending` (warning, action `review` → the approvals dialog).
  The item's `uid` is a fingerprint of the set, so ignoring one ignores exactly
  that set and the item returns when the set changes. They count toward the
  sidebar badges and the menu-bar number through `counts_by_kind`.
- **BREAKING** `POST /api/v1/secrets/approvals/{id}/ask-again` and
  `SecretBoundary.ask_again` are removed. A refusal still withholds the secret
  (`SECRET_BINDING_REJECTED`) and still stands for its target until the
  destination changes; a rejection still records its audit event.
- The channel and CLI messages that told a person to ask again no longer do.
- The Secrets page is one table (status filter, Used by, relative times, a
  selection bar for deleting several), its missing-value banner offers **Add
  values** instead of importing a master key, the approvals dialog is one table
  answered in one step, and both banners can be ignored like Overview's.

## Impact

- `secret` spec: ADDED "List secrets with no value here and waiting approvals on Overview";
  MODIFIED "Hold a secret for a new destination until a person approves it",
  "Show a secret this Mac cannot open as missing on this Mac" and "Approve
  several bindings in one confirmation".
- `web-ui` spec: MODIFIED "Manage stored secrets on the Secrets page".
- `channels` spec: MODIFIED "Report a channel whose secret waits for approval".
- Frontend: the Secrets page agent removes `RefusedApprovalsEntry` and its
  hooks; the API client functions for the deleted route are already gone.
