// frontend/src/components/knowledge/KnowledgeNav.tsx
//
// The Knowledge page's left pane: Recent changes on top (with how many changes
// the last seven days hold), then every collection as a node of one tree —
// its Inbox and its documents under it — and New collection at the bottom
// (spec knowledge "Present a collection as one tree in the web UI"). The open
// collection is expanded; others open and close on their chevron, and that
// choice is ephemeral UI state (it does not survive a reload).
//
// There is no filter input: the layer has no retrieval, and ⌘K already jumps
// to a collection by name.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { History, Plus } from "lucide-react";

import { KnowledgeCollectionNode } from "@/components/knowledge/KnowledgeCollectionNode";
import { NAV_ROW, NAV_ROW_ACTIVE, NAV_ROW_IDLE } from "@/components/knowledge/navRow";
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
    <nav aria-label={t("knowledge.nav.label")} className="space-y-4 pb-4">
      <Link
        to={KNOWLEDGE_ROOT}
        aria-current={props.atRecent ? "page" : undefined}
        className={cn(NAV_ROW, "pl-1", props.atRecent ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
      >
        <History className="size-4 shrink-0 opacity-70" aria-hidden />
        <span className="truncate">{t("knowledge.recent.title")}</span>
        {recent > 0 ? (
          <span className="ml-auto text-xs tabular-nums text-text-subtle">{recent}</span>
        ) : null}
      </Link>

      <div className="space-y-0.5">
        <p className="flex items-center gap-1.5 px-1 pb-1 text-2xs font-semibold text-text-subtle">
          {t("knowledge.nav.collections")}
          <span className="tabular-nums">{props.collections.length}</span>
        </p>
        {props.isLoading ? (
          <div className="space-y-2 px-1" aria-busy>
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : (
          <ul className="space-y-0.5">
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
        <button
          type="button"
          onClick={props.onCreate}
          className={cn(NAV_ROW, NAV_ROW_IDLE, "pl-1")}
        >
          <Plus className="size-4 shrink-0 opacity-70" aria-hidden />
          <span>{t("knowledge.create.title")}</span>
        </button>
      </div>
    </nav>
  );
}
