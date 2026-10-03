// frontend/src/components/knowledge/KnowledgeNav.tsx
//
// The Knowledge page's left pane (boards 5.1.01, 5.1.09, Foundations 0.6.04):
// Recent changes on top, then a 36px "Collections" header strip with a New
// collection icon button, then every collection as a node of one tree — its
// Inbox and its documents under it (spec knowledge "Present a collection as
// one tree in the web UI"). The open collection is expanded; others open and
// close on their chevron, and that choice is ephemeral UI state (it does not
// survive a reload).
//
// There is no filter input: the layer has no retrieval, and ⌘K already jumps
// to a collection by name. The Inbox count in the tree is the only number and
// the only signal of items waiting — the sidebar carries no badge.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { FolderPlus, History } from "lucide-react";

import { KnowledgeCollectionNode } from "@/components/knowledge/KnowledgeCollectionNode";
import {
  NAV_CHEVRON,
  NAV_ICON,
  NAV_LABEL,
  NAV_ROW,
  NAV_ROW_ACTIVE,
  NAV_ROW_IDLE,
  navIndent,
} from "@/components/knowledge/navRow";
import { ListLoadingRows } from "@/components/ListPaneStates";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CollectionOut } from "@/lib/api/knowledge";
import { KNOWLEDGE_ROOT, type KnowledgeTab } from "@/lib/knowledge/routes";
import { cn } from "@/lib/utils";

interface Props {
  collections: CollectionOut[];
  isLoading: boolean;
  currentUid: string | null;
  tab: KnowledgeTab;
  file: string | null;
  /** The pane is on Recent changes (the page's bare address). */
  atRecent: boolean;
  modelSet: boolean | undefined;
  onCreate: () => void;
}

export function KnowledgeNav(props: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<Set<string>>(new Set());

  const toggle = (uid: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });

  return (
    <nav aria-label={t("knowledge.nav.label")} className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-px overflow-auto px-2 py-2.5">
        <Link
          to={KNOWLEDGE_ROOT}
          aria-current={props.atRecent ? "page" : undefined}
          style={navIndent(0)}
          className={cn(NAV_ROW, props.atRecent ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
        >
          <span className={NAV_CHEVRON} />
          <History className={NAV_ICON} aria-hidden />
          <span className={cn(NAV_LABEL, props.atRecent && "font-label")}>
            {t("knowledge.recent.title")}
          </span>
        </Link>

        <div className="-mx-2 mb-1 mt-2 flex h-9 shrink-0 items-center border-y border-border-subtle pl-[18px] pr-2.5 text-sm font-semibold text-text">
          {t("knowledge.nav.collections")}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="ml-auto"
                aria-label={t("knowledge.create.title")}
                onClick={props.onCreate}
              >
                <FolderPlus aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("knowledge.create.title")}</TooltipContent>
          </Tooltip>
        </div>
        {props.isLoading ? (
          <ListLoadingRows />
        ) : (
          <ul className="flex flex-col gap-px">
            {props.collections.map((c) => (
              <KnowledgeCollectionNode
                key={c.uid}
                collection={c}
                // The open collection is always expanded; a click on its
                // chevron closes it only while it is not the one on screen.
                expanded={c.uid === props.currentUid ? !open.has(c.uid) : open.has(c.uid)}
                onToggle={() => toggle(c.uid)}
                current={c.uid === props.currentUid}
                tab={props.tab}
                file={props.file}
                modelSet={props.modelSet}
              />
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}
