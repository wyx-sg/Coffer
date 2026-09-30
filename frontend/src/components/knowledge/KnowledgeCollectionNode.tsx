// frontend/src/components/knowledge/KnowledgeCollectionNode.tsx
//
// One collection in the Knowledge tree: its row (chevron, name, how many
// documents), and while expanded its Inbox node and its documents. The Inbox
// node carries the number of items waiting and opens the Inbox view — the one
// place Curate now lives (spec knowledge "Present a collection as one tree in
// the web UI"). With Coffer's model not set there is no Inbox node at all:
// items become documents as they arrive, so there is never anything waiting.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, Inbox, Library } from "lucide-react";

import { NAV_ROW, NAV_ROW_ACTIVE, NAV_ROW_IDLE } from "@/components/knowledge/navRow";
import { KnowledgeTreeLevel } from "@/components/knowledge/KnowledgeTreeLevel";
import type { CollectionOut } from "@/lib/api/knowledge";
import { collectionPath, type KnowledgeTab } from "@/lib/knowledge/routes";
import { cn } from "@/lib/utils";

interface Props {
  collection: CollectionOut;
  expanded: boolean;
  onToggle: () => void;
  /** This collection is the one on screen. */
  current: boolean;
  tab: KnowledgeTab;
  file: string | null;
  modelSet: boolean | undefined;
}

export function KnowledgeCollectionNode({
  collection,
  expanded,
  onToggle,
  current,
  tab,
  file,
  modelSet,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const label = collection.title || collection.name;
  const onOverview = current && tab !== "inbox" && !file;
  const onInbox = current && tab === "inbox";
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <li>
      <div className={cn(NAV_ROW, "gap-0 p-0", onOverview ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={t(expanded ? "knowledge.nav.collapse" : "knowledge.nav.expand", {
            name: label,
          })}
          className="flex size-6 shrink-0 items-center justify-center rounded-sm"
        >
          <Chevron className="size-3.5 opacity-70" aria-hidden />
        </button>
        <button
          type="button"
          onClick={() => navigate(collectionPath(collection.uid))}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pr-2 text-left"
        >
          <Library className="size-4 shrink-0 opacity-70" aria-hidden />
          <span className="truncate">{label}</span>
          <span className="ml-auto shrink-0 text-xs tabular-nums text-text-subtle">
            {collection.document_count}
          </span>
        </button>
      </div>

      {expanded ? (
        <div className="pl-4">
          {modelSet ? (
            <button
              type="button"
              onClick={() => navigate(collectionPath(collection.uid, "inbox"))}
              aria-current={onInbox ? "page" : undefined}
              className={cn(NAV_ROW, "pl-1", onInbox ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
            >
              <Inbox className="size-4 shrink-0 opacity-70" aria-hidden />
              <span className="truncate">{t("knowledge.inbox.title")}</span>
              <span
                className="ml-auto shrink-0 text-xs tabular-nums text-text-subtle"
                aria-label={t("knowledge.inbox.waitingCount", { count: collection.pending_count })}
              >
                {collection.pending_count}
              </span>
            </button>
          ) : null}
          <KnowledgeTreeLevel
            path={collection.name}
            depth={0}
            selectedPath={current && tab !== "inbox" ? file : null}
            onSelect={(path) => navigate(collectionPath(collection.uid, "document", path))}
            emptyLabel={t("knowledge.tree.empty")}
          />
        </div>
      ) : null}
    </li>
  );
}
