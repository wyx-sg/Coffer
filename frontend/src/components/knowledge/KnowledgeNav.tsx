// frontend/src/components/knowledge/KnowledgeNav.tsx
//
// The Knowledge page's left pane (boards 5.1.01, 5.1.09): Recent changes on
// top (with how many changes the last seven days hold), then every collection
// as a node of one tree — its Inbox and its documents under it — and New
// collection pinned to the bottom (spec knowledge "Present a collection as
// one tree in the web UI"). The open collection is expanded; others open and
// close on their chevron, and that choice is ephemeral UI state (it does not
// survive a reload).
//
// There is no filter input: the layer has no retrieval, and ⌘K already jumps
// to a collection by name. The Inbox count in the tree is the only signal of
// items waiting — the sidebar carries no badge for it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { History, Plus } from "lucide-react";

import { KnowledgeCollectionNode } from "@/components/knowledge/KnowledgeCollectionNode";
import {
  NAV_CHEVRON,
  NAV_ICON,
  NAV_LABEL,
  NAV_PILL,
  NAV_ROW,
  NAV_ROW_ACTIVE,
  NAV_ROW_IDLE,
  navIndent,
} from "@/components/knowledge/navRow";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut } from "@/lib/api/knowledge";
import { withinDays } from "@/lib/knowledge/changes";
import { KNOWLEDGE_ROOT, type KnowledgeTab } from "@/lib/knowledge/routes";
import { useKnowledgeChanges } from "@/lib/hooks/useKnowledgeHistory";
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
  const changes = useKnowledgeChanges(null);
  const recent = (changes.data?.changes ?? []).filter((c) => withinDays(c.time, 7)).length;
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
          <span className={NAV_LABEL}>{t("knowledge.recent.title")}</span>
          {recent > 0 ? (
            <span className={cn(NAV_PILL, "bg-chip text-text-muted")}>{recent}</span>
          ) : null}
        </Link>

        <div className="h-2 shrink-0" />
        <p className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-subtle">
          {t("knowledge.nav.collections")}
          <span className="ml-auto font-book tabular-nums">{props.collections.length}</span>
        </p>
        {props.isLoading ? (
          <div className="space-y-2 px-2" aria-busy>
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
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
      <button
        type="button"
        onClick={props.onCreate}
        className="flex h-10 shrink-0 items-center gap-2 border-t border-border-subtle px-[18px] text-sm text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
      >
        <Plus className="size-3.5 shrink-0" aria-hidden />
        <span>{t("knowledge.create.title")}</span>
      </button>
    </nav>
  );
}
