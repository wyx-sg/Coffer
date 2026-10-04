// frontend/src/components/knowledge/KnowledgeCollectionNode.tsx
//
// One collection in the Knowledge tree: its row (chevron, folder, its folder
// name — no document count), and while expanded its documents. A collection
// has no title — the tree names it by its folder.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, Folder, FolderOpen } from "lucide-react";

import {
  NAV_CHEVRON,
  NAV_FOLDER,
  NAV_ICON,
  NAV_ROW,
  NAV_ROW_ACTIVE,
  NAV_ROW_IDLE,
  navIndent,
} from "@/components/knowledge/navRow";
import { KnowledgeTreeLevel } from "@/components/knowledge/KnowledgeTreeLevel";
import type { CollectionOut } from "@/lib/api/knowledge";
import { collectionPath } from "@/lib/knowledge/routes";
import { cn } from "@/lib/utils";

interface Props {
  collection: CollectionOut;
  expanded: boolean;
  onToggle: () => void;
  /** This collection is the one on screen. */
  current: boolean;
  file: string | null;
}

export function KnowledgeCollectionNode({ collection, expanded, onToggle, current, file }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const name = collection.name;
  const onOverview = current && !file;
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
          <KnowledgeTreeLevel
            path={name}
            depth={1}
            selectedPath={current ? file : null}
            onSelect={(path) => navigate(collectionPath(collection.uid, "document", path))}
            emptyLabel={t("knowledge.tree.empty")}
          />
        </div>
      ) : null}
    </li>
  );
}
