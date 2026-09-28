// frontend/src/components/knowledge/KnowledgeBrowser.tsx
//
// A collection's documents: the tree on the left, the document chosen from it
// in the pane on the right (spec knowledge "Present a collection as one tree in
// the web UI"). The tree's root is the
// collection directory itself — there is one tree, and every document in it is
// one people and curation write together.
//
// There is no input above the tree: the layer exposes no retrieval anywhere
// (see "Expose exactly one knowledge tool"), and a name filter over a tree that
// loads one level at a time could only ever narrow what was already open. An
// agent reads the files with its own tools; a person reads them through this
// tree. Both panes reach the bottom of the window and scroll inside
// (components/filePane.ts).
import { useTranslation } from "react-i18next";

import { KnowledgeFilePreview } from "@/components/knowledge/KnowledgeFilePreview";
import { KnowledgeTreeLevel } from "@/components/knowledge/KnowledgeTreeLevel";
import {
  FILE_PANE_COLUMN,
  FILE_PANE_GRID,
  FILE_PANE_SCROLL,
  useFillToBottom,
} from "@/components/filePane";
import { cn } from "@/lib/utils";

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
  const fill = useFillToBottom();

  return (
    // The skill Files tab's proportions, so the two browsers sit the same way
    // on the page.
    <div
      ref={fill.ref}
      style={fill.style}
      className={cn(FILE_PANE_GRID, "md:grid-cols-[18rem_minmax(0,1fr)]")}
    >
      <div className={FILE_PANE_COLUMN}>
        <nav aria-label={t("knowledge.detail.treeLabel")} className={FILE_PANE_SCROLL}>
          <KnowledgeTreeLevel
            path={collection}
            depth={0}
            selectedPath={selected}
            onSelect={onSelect}
            emptyLabel={t("knowledge.detail.empty")}
          />
        </nav>
      </div>

      <KnowledgeFilePreview path={selected} onDeleted={() => onSelect(null)} />
    </div>
  );
}
