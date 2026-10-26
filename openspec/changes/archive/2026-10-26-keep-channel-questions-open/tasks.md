## 1. Decision and specs

- [x] 1.1 ADR `a-question-outlives-the-turn-that-asked-it`; README index
- [x] 1.2 Edit `openspec/specs/chat/spec.md` and `openspec/specs/channels/spec.md` directly (`skip_specs: true`)

## 2. Backend

- [x] 2.1 `close_turn(keep_open=)`; outlived questions survive `release_turn`, expire after 24 h, are superseded by a new question
- [x] 2.2 Channel cards of a finished turn stay; a late tap or text answer rewrites them and starts the next turn
- [x] 2.3 Group question cards @mention the asker and carry their own 🗑
- [x] 2.4 Channel note: wait for the answer or end the turn silently
- [x] 2.5 Acceptance and unit tests

## 3. Docs and design

- [x] 3.1 docs-site guide, en and zh
- [x] 3.2 Design canvas updated
