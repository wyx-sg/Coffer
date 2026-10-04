## 1. Backend

- [x] 1.1 `SecretAttentionSource` reports `secret_missing_here` and `secret_approvals_pending`, fingerprinted in `uid`; wired in `attention_wiring.py`
- [x] 1.2 Remove the ask-again route, `SecretBoundary.ask_again` and the messages that point at it
- [x] 1.3 Tests: attention items and keys (unit + daemon), refused binding stays refused
- [x] 1.4 `make contracts`

## 2. Frontend client

- [x] 2.1 Remove `askAgain` / `refusedApprovals` API calls and their hooks
- [ ] 2.2 Secrets page: banners with × (Ignore), delete `RefusedApprovalsEntry` (Secrets page work item)
