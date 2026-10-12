// frontend/src/components/knowledge/KnowledgeNav.tsx
//
// The Knowledge page's left pane (boards 5.1.01, 5.1.09, Foundations 0.6.04):
// a 36px "Collections" header strip with a New collection icon button, then
// every collection as a node of one tree — its documents under it (spec
// knowledge "Show a collection as one tree of read-only documents in the web
// UI"). The open collection is expanded unless closed on
// its chevron; others open and close on theirs, and that choice is kept in the
// browser (lib/knowledge/treeState.ts), so the tree comes back as it was left.
//
// There is no filter input: the layer has no retrieval, and ⌘K already jumps
// to a collection by name.
import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { FolderPlus } from "lucide-react";

import { KnowledgeCollectionNode } from "@/components/knowledge/KnowledgeCollectionNode";
import { ListLoadingRows } from "@/components/ListPaneStates";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CollectionOut } from "@/lib/api/knowledge";
import { clearTreeClosed, useTreeState } from "@/lib/knowledge/treeState";

interface Props {
  collections: CollectionOut[];
  isLoading: boolean;
  currentUid: string | null;
  file: string | null;
  onCreate: () => void;
}

export function KnowledgeNav(props: Props) {
  const { t } = useTranslation();
  // What the person opened and closed on a chevron. The collection on screen
  // is open unless they closed it; opening one first and then navigating into
  // it keeps it open rather than flipping it shut.
  const { opened, closed, setOpen } = useTreeState("collections");
  // Arriving in a collection — a document, a link — opens it again even if it was closed earlier, so what is on
  // screen is visible in the tree. A layout effect, so the tree never paints
  // closed first; not on mount, so coming back finds the tree as it was left.
  const arrivedAt = useRef(props.currentUid);
  useLayoutEffect(() => {
    if (arrivedAt.current === props.currentUid) return;
    arrivedAt.current = props.currentUid;
    if (props.currentUid) clearTreeClosed("collections", props.currentUid);
  }, [props.currentUid]);
  const isOpen = (uid: string) => !closed.has(uid) && (opened.has(uid) || uid === props.currentUid);
  const toggle = (uid: string) => setOpen(uid, !isOpen(uid));

  return (
    <nav aria-label={t("knowledge.nav.label")} className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-px overflow-auto px-2 py-2.5">
        <div className="-mx-2 mb-1 flex h-9 shrink-0 items-center border-y border-border-subtle pl-[18px] pr-2.5 text-sm font-semibold text-text">
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
                expanded={isOpen(c.uid)}
                onToggle={() => toggle(c.uid)}
                current={c.uid === props.currentUid}
                file={props.file}
              />
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}
