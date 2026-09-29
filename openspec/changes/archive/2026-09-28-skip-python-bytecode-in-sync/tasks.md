## 1. Bytecode

- [x] 1.1 `_tree_files(..., bytecode=False)` on the source side of `_mirror_tree`; the destination side still sees bytecode, so an older build's copies are deleted
- [x] 1.2 Tree mirror tests with acceptance markers

## 2. CLI summary

- [x] 2.1 `_counts` prints only integer tallies
- [x] 2.2 Sync CLI test asserts no per-path list in the summary
