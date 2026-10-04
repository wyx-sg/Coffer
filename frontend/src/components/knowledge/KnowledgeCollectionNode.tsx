// frontend/src/components/knowledge/KnowledgeCollectionNode.tsx
//
// One collection in the Knowledge tree: its row (chevron, folder, its folder
// name — no document count), and while expanded its Inbox node and its
// documents. A collection has no title — the tree names it by its folder.
// The Inbox node carries the number of items waiting, in 11 text-subtle and
// never as "0" — the tree's only count and the only signal of them (the
// sidebar has no badge) — and opens the Inbox view; while that view is
// open it expands to list the items, each opening read-only (boards 5.1.09,
// 5.1.26), and its own chevron closes and reopens that list. With Coffer's model not set there is no Inbox node at all: items
// become documents as they arrive, so there is never anything waiting.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Inbox } from "lucide-react";

import {
  NAV_CHEVRON,
  NAV_COUNT,
  NAV_FOLDER,
  NAV_ICON,
  NAV_LABEL,
  NAV_NAME,
  NAV_ROW,
  NAV_ROW_ACTIVE,
  NAV_ROW_IDLE,
  navIndent,
} from "@/components/knowledge/navRow";
import { KnowledgeTreeLevel } from "@/components/knowledge/KnowledgeTreeLevel";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeTree } from "@/lib/hooks/useKnowledge";
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
  const name = collection.name;
  const onOverview = current && tab !== "inbox" && !file;
  const onInbox = current && tab === "inbox";
  const Chevron = expanded ? ChevronDown : ChevronRight;
  const FolderIcon = expanded ? FolderOpen : Folder;

  return (
    <li>
      <div
        style={navIndent(0)}
        className={cn(NAV_ROW, "gap-0", onOverview ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
      >
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={t(expanded ? "knowledge.nav.collapse" : "knowledge.nav.expand", { name })}
          className={cn(NAV_CHEVRON, "h-full")}
        >
          <Chevron className="size-3" aria-hidden />
        </button>
        <button
          type="button"
          onClick={() => navigate(collectionPath(collection.uid))}
          aria-current={onOverview ? "page" : undefined}
          className="flex h-full min-w-0 flex-1 items-center gap-1.5 pl-1.5 text-left"
        >
          <FolderIcon className={NAV_ICON} aria-hidden />
          <span className={cn(NAV_FOLDER, onOverview && "font-label")}>{name}</span>
        </button>
      </div>

      {expanded ? (
        <div className="flex flex-col gap-px">
          {modelSet ? (
            <InboxNode
              collection={collection}
              open={onInbox}
              selected={onInbox ? file : null}
              onOpen={() => navigate(collectionPath(collection.uid, "inbox"))}
              onSelect={(path) => navigate(collectionPath(collection.uid, "inbox", path))}
            />
          ) : null}
          <KnowledgeTreeLevel
            path={name}
            depth={1}
            selectedPath={current && tab !== "inbox" ? file : null}
            onSelect={(path) => navigate(collectionPath(collection.uid, "document", path))}
            emptyLabel={t("knowledge.tree.empty")}
          />
        </div>
      ) : null}
    </li>
  );
}

interface InboxNodeProps {
  collection: CollectionOut;
  /** The Inbox view is on screen: the node is current and lists its items. */
  open: boolean;
  selected: string | null;
  onOpen: () => void;
  onSelect: (path: string) => void;
}

function InboxNode({ collection, open, selected, onOpen, onSelect }: InboxNodeProps) {
  const { t } = useTranslation();
  const count = collection.pending_count;
  // Listed while the Inbox view is open, unless closed on the chevron; the
  // chevron also lists it from anywhere else, like any folder.
  const [listed, setListed] = useState<boolean | null>(null);
  const expanded = count > 0 && (listed ?? open);
  const items = useKnowledgeTree(`${collection.name}/.inbox`, expanded);
  const Chevron = expanded ? ChevronDown : ChevronRight;
  const name = t("knowledge.inbox.title");
  return (
    <>
      <div
        style={navIndent(1)}
        className={cn(NAV_ROW, "gap-0", open && !selected ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
      >
        {count > 0 ? (
          <button
            type="button"
            onClick={() => setListed(!expanded)}
            aria-expanded={expanded}
            aria-label={t(expanded ? "knowledge.nav.collapse" : "knowledge.nav.expand", { name })}
            className={cn(NAV_CHEVRON, "h-full")}
          >
            <Chevron className="size-3" aria-hidden />
          </button>
        ) : (
          <span className={NAV_CHEVRON} />
        )}
        <button
          type="button"
          onClick={() => {
            setListed(true);
            onOpen();
          }}
          aria-current={open && !selected ? "page" : undefined}
          className="flex h-full min-w-0 flex-1 items-center gap-1.5 pl-1.5 text-left"
        >
          <Inbox className={NAV_ICON} aria-hidden />
          <span className={cn(NAV_LABEL, open && "font-label")}>{name}</span>
          {count > 0 ? (
            <span className={NAV_COUNT} aria-label={t("knowledge.inbox.waitingCount", { count })}>
              {count}
            </span>
          ) : null}
        </button>
      </div>
      {expanded
        ? (items.data?.files ?? []).map((item) => {
            const active = selected === item.path;
            return (
              <button
                key={item.path}
                type="button"
                onClick={() => onSelect(item.path)}
                aria-current={active ? "page" : undefined}
                style={navIndent(2)}
                className={cn(NAV_ROW, active ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
              >
                <span className={NAV_CHEVRON} />
                <FileText className={NAV_ICON} aria-hidden />
                <span className={cn(NAV_NAME, active && "font-label")}>
                  {item.path.split("/").pop()}
                </span>
              </button>
            );
          })
        : null}
    </>
  );
}
