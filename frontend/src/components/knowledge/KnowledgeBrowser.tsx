// frontend/src/components/knowledge/KnowledgeBrowser.tsx
//
// A collection's documents: the tree on the left, the document chosen from it
// in the pane on the right (spec knowledge FR-040). The tree's root is the
// collection directory itself — there is one tree, and every document in it is
// one people and curation write together.
//
// The input above the tree is a FILTER, not a query. It narrows the names
// already on screen as the user types — no request, no debounce, no ranking —
// because this layer exposes no retrieval anywhere (FR-033, FR-040). An agent
// reads the files with its own tools; a person reads them through this tree.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeFilePreview } from "@/components/knowledge/KnowledgeFilePreview";
import { KnowledgeTreeLevel } from "@/components/knowledge/KnowledgeTreeLevel";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { Input } from "@/components/ui/input";

interface Props {
  /** The collection's NAME — its directory, and so the tree's root path. `""`
   *  while the page is still resolving it, which the tree treats as "nothing
   *  to ask for" rather than firing a request for the knowledge root. */
  collection: string;
  /** Knowledge-root-relative path of the document being previewed, if any. */
  selected: string | null;
  onSelect: (path: string | null) => void;
}

export function KnowledgeBrowser({ collection, selected, onSelect }: Props) {
  const { t } = useTranslation();
  // Deliberately NOT in the URL: a half-typed filter is draft input, not
  // addressable state (agents/frontend.md §3).
  const [filter, setFilter] = useState("");
  const treeLabel = t("knowledge.detail.treeLabel");

  return (
    // The skill Files tab's proportions, so the two browsers sit the same way
    // on the page.
    <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
      <div className="space-y-2">
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("knowledge.detail.filterPlaceholder")}
          aria-label={t("knowledge.detail.filterPlaceholder")}
        />
        <nav aria-label={treeLabel} className={FILE_PANE_MAX_HEIGHT}>
          <KnowledgeTreeLevel
            path={collection}
            depth={0}
            selectedPath={selected}
            filter={filter}
            onSelect={onSelect}
            emptyLabel={t("knowledge.detail.empty")}
          />
        </nav>
      </div>

      <KnowledgeFilePreview path={selected} onDeleted={() => onSelect(null)} />
    </div>
  );
}
