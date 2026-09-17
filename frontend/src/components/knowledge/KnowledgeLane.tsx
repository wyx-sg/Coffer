// frontend/src/components/knowledge/KnowledgeLane.tsx
//
// ONE lane of a collection: its tree on the left, the file chosen from it in
// the pane on the right (spec knowledge FR-040). The page mounts this twice,
// once per lane, and the two behave identically except for what may be done to
// a file — which `KnowledgeFilePreview` decides from the lane, not from here.
//
// The `topics/` lane carries a notice, because a reader who has just found the
// document holding the fact they wanted will reach for the edit that is not
// there. It says who wrote it, that an edit here is overwritten by the next
// pass, and where a correction actually goes: in as a new source.
//
// The input above the tree is a FILTER, not a query. It narrows the names
// already on screen as the user types — no request, no debounce, no ranking —
// because this layer exposes no retrieval anywhere (FR-033, FR-040). An agent
// reads the files with its own tools; a person reads them through this tree.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import { KnowledgeFilePreview } from "@/components/knowledge/KnowledgeFilePreview";
import { KnowledgeTreeLevel } from "@/components/knowledge/KnowledgeTreeLevel";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { Input } from "@/components/ui/input";
import { lanePath, type KnowledgeLane as Lane } from "@/lib/knowledge/lanes";

interface Props {
  collection: string;
  lane: Lane;
  /** Knowledge-root-relative path of the file being previewed, if any. */
  selected: string | null;
  onSelect: (path: string | null) => void;
}

export function KnowledgeLane({ collection, lane, selected, onSelect }: Props) {
  const { t } = useTranslation();
  // Per-lane and deliberately NOT in the URL: a half-typed filter is draft
  // input, not addressable state (agents/frontend.md §3).
  const [filter, setFilter] = useState("");
  const treeLabel = t(`knowledge.detail.lanes.${lane}.treeLabel`);

  return (
    <div className="space-y-4">
      {lane === "topics" ? (
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <Sparkles className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>{t("knowledge.detail.lanes.topics.writtenByCuration")}</span>
        </p>
      ) : null}

      {/* The skill Files tab's proportions, so the two browsers sit the same
          way on the page. */}
      <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
        <div className="space-y-2">
          <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {treeLabel}
          </p>
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("knowledge.detail.filterPlaceholder")}
            aria-label={t("knowledge.detail.filterPlaceholder")}
          />
          <nav aria-label={treeLabel} className={FILE_PANE_MAX_HEIGHT}>
            <KnowledgeTreeLevel
              path={lanePath(collection, lane)}
              depth={0}
              selectedPath={selected}
              filter={filter}
              onSelect={onSelect}
              emptyLabel={t(`knowledge.detail.lanes.${lane}.empty`)}
            />
          </nav>
        </div>

        <KnowledgeFilePreview path={selected} lane={lane} onDeleted={() => onSelect(null)} />
      </div>
    </div>
  );
}
