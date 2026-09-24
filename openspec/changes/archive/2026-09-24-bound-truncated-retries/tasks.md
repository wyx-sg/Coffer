## 1. Bound the retries

- [x] 1.1 Count consecutive cut-offs per item; settle on the third and report `gave_up` — tests carry acceptance(knowledge, "a pass cut off by the recursion limit reports it and leaves its item owed")
- [x] 1.2 Queue a cut-off item behind the rest of the inbox on the next sweep
- [x] 1.3 Add `gave_up` to `CurationOut`, the contract and data-model; regenerate the client; web message for a pass that gave up

## 2. Close

- [x] 2.1 Run `make verify`
- [x] 2.2 Archive the change
