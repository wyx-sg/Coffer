## Why

The two version histories in the web UI looked and worked differently: a skill's
History was a split with a divider that barely moved left, and a knowledge
document's History expanded each version in place. Their diffs came from two
renderers, one of which cut long lines off.

## What Changes

- One version-history split (`components/history/VersionHistorySplit.tsx`) for
  the Skill and Knowledge History tabs: versions on the left, the chosen
  version's diff file by file on the right. The divider narrows the list to
  160 px.
- Knowledge History moves onto it: the newest version is chosen when the tab
  opens, and the version's switch, Restore and See the pass sit on the right.
- One diff renderer, `FileDiff`: long lines wrap with a ↳ continuation marker.
  `KnowledgeDiff` is removed and its callers draw through `FileDiff`.

## Impact

- Frontend: `components/history/`, `components/change-preview/FileDiff.tsx`,
  `components/skills/SkillHistoryTab.tsx`, `components/knowledge/KnowledgeHistoryTab.tsx`,
  `KnowledgeVersionPanel.tsx`, `KnowledgeChangeView.tsx`, `KnowledgeCompareView.tsx`.
- Specs: web-ui.
- Docs: guides/knowledge (History), guides/skills.
