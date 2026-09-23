## 1. Scenarios

- [x] 1.1 channels: "pairing from another account replaces the owner" — test carries acceptance(channels, "pairing from another account replaces the owner")
- [x] 1.2 knowledge: "a pass cut off by the recursion limit reports it and leaves its item owed" — test carries its marker; contract `CurationOut.status` gains `truncated`, codegen re-run
- [x] 1.3 vault-sync: "a curation pass is skipped while a round is unresolved" — test carries its marker

## 2. Close

- [x] 2.1 Run `make verify`
- [x] 2.2 Archive the change
