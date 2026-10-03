## 1. Backend

- [x] 1.1 Delete the quota service, parsers, repo, Codex rate-limit reader, statusline hand-off and the chat quota observer chain
- [x] 1.2 Delete `/usage/quota*` routes and schemas, `coffer usage quota|statusline`, `COFFER_QUOTA_POLL`
- [x] 1.3 Migration 0140 drops `quota_snapshots`
- [x] 1.4 Regenerate the contracts

## 2. Frontend

- [x] 2.1 Delete `/usage`, `UsagePage`, `QuotaSection`/`QuotaCard`/`QuotaMeter`, `RangeControl`, `CustomRangePopover`, the quota queries and the Updated / Refresh header
- [x] 2.2 Model providers header with Providers | Usage tabs, `?tab=usage`, Experimental tag, Add provider on both
- [x] 2.3 Usage tab: shared time-range pill (dates only), Agent and Provider pills, Export CSV on the row
- [x] 2.4 Five frameless tiles with the price note behind Cost's "?"; data-colour chart; segmented breakdown; bordered table with Total and "Edit prices"; "Show all" by day
- [x] 2.5 First run: whole-page empty state with Open Providers
- [x] 2.6 Sidebar, palette and Overview: no Usage entry; the Overview tile opens the Usage tab

## 3. Specs and checks

- [x] 3.1 Deltas for web-ui, provider-switching, experimental-features
- [x] 3.2 Acceptance markers follow the scenarios; e2e follows the new address
