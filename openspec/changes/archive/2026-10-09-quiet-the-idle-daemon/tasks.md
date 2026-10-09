## 1. Hot spots

- [x] 1.1 The invocation writer blocks on its queue; `stop()` wakes it with a marker; drop `flush_interval_seconds`
- [x] 1.2 The vault watch uses a 500 ms step and a 60 s native timeout
- [x] 1.3 Tests: an idle writer stops at once and loses no row; a file event wakes the scanner and a cancel returns within the step

## 2. Quiet periodic passes

- [x] 2.1 A periodic pass that changed nothing tells no pass listener
- [x] 2.2 Test: the listener hears a first finding, a hinted pass, a repair and a closed difference, and not a repeat

## 3. Docs

- [x] 3.1 model-proxy, reconciler and daemon architecture pages (en + zh)
