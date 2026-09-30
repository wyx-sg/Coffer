// frontend/src/components/memory/PartitionMemoriesTab.tsx — a partition's Memories tab.
//
// A resizable split (spec memory "Present a partition as its memories"): the
// partition's memories with their collapsed Retired group on the left, the
// selected memory on the right; both reach the bottom of the window and
// scroll inside. The selected memory is the `?memory=<slug>` search param —
// the first memory when none is named.
//
// What the page leaves out is the requirement too: no file tree, no
// `MEMORY.md` / `RETIRED.md`, no `.raw/`, no native path and no agent's
// original text. The partition's file listing is read only to find the
// selected memory's own file for open-in-editor and reveal.
import { useSearchParams } from "react-router-dom";
import { Brain } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { FILE_PANE_COLUMN, FILE_PANE_SCROLL, useFillToBottom } from "@/components/filePane";
import { MemoryList } from "@/components/memory/MemoryList";
import { MemoryPane } from "@/components/memory/MemoryPane";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { NoModelNotice } from "@/components/memory/NoModelNotice";
import { SplitView } from "@/components/SplitView";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { agentTypeLabel } from "@/lib/agents/display";
import type { MemoryFileNode, PartitionOut } from "@/lib/api/memoryTypes";
import { agentTypeOfOrigin } from "./memoryAgents";
import { useCofferModelSet } from "@/lib/hooks/useInternalEngine";
import { useMemoryNotes, useMemoryRetired, usePartitionFiles } from "@/lib/hooks/useMemory";

/** The search param naming the selected memory. */
const MEMORY_PARAM = "memory";

interface Props {
  uid: string;
  /** The partition's display name, for the empty state. */
  name: string;
  /** A distil pass over this partition is running. */
  running: boolean;
  /** The partition's row: its sources decide "All agents", and entries read
   *  but not distilled yet are what an empty list says it is waiting on. */
  partition?: PartitionOut;
}

/** The node at `path` (relative to the partition directory), if any. */
function findNode(node: MemoryFileNode | undefined, path: string): MemoryFileNode | null {
  if (!node) return null;
  if (node.path === path) return node;
  for (const child of node.children) {
    const hit = findNode(child, path);
    if (hit) return hit;
  }
  return null;
}

export function PartitionMemoriesTab({ uid, name, running, partition }: Props) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const notes = useMemoryNotes(uid);
  const retired = useMemoryRetired(uid);
  const files = usePartitionFiles(uid);
  const modelSet = useCofferModelSet();
  const fill = useFillToBottom();

  const memories = notes.data ?? [];
  const wanted = params.get(MEMORY_PARAM);
  const selected = memories.find((m) => m.slug === wanted)?.slug ?? memories[0]?.slug ?? null;
  const select = (slug: string) => {
    const next = new URLSearchParams(params);
    next.set(MEMORY_PARAM, slug);
    setParams(next, { replace: true });
  };
  const filePath = selected
    ? (findNode(files.data, `notes/${selected}.md`)?.abs_path ?? null)
    : null;

  const notice = modelSet === false ? <NoModelNotice /> : null;

  if (notes.isPending) {
    return (
      <div className="space-y-2" aria-busy="true">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-10 w-80" />
      </div>
    );
  }
  if (notes.error) {
    return (
      <EmptyState
        icon={Brain}
        tone="error"
        title={t("memory.memories.loadFailed")}
        description={translateApiError(t, notes.error)}
      />
    );
  }
  if (memories.length === 0) {
    return (
      <div className="space-y-4">
        {notice}
        <EmptyState
          icon={Brain}
          title={t("memory.memories.emptyTitle", { name })}
          description={
            partition && partition.waiting_entries > 0
              ? t("memory.memories.emptyWaiting", {
                  count: partition.waiting_entries,
                  agents: [...new Set(partition.waiting_agents.map(agentTypeOfOrigin))]
                    .map(agentTypeLabel)
                    .join(", "),
                })
              : t("memory.memories.emptyBody")
          }
          action={<MemoryUpdateButton running={running} />}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-col gap-4">
      {notice}
      <div ref={fill.ref} style={fill.style} className="flex min-h-0">
        <SplitView
          storageKey="memory-partition"
          label={t("splitView.resizeList")}
          className="min-h-0 flex-1"
          listClassName={FILE_PANE_COLUMN}
          detailClassName="flex min-h-0 flex-col pl-4"
          list={
            <div className={FILE_PANE_SCROLL}>
              <MemoryList
                memories={memories}
                retired={retired.data ?? []}
                selected={selected}
                onSelect={select}
                sources={partition?.sources ?? []}
              />
            </div>
          }
          detail={
            selected ? (
              <MemoryPane uid={uid} slug={selected} filePath={filePath} />
            ) : (
              <p className="text-sm text-text-muted">{t("memory.memories.select")}</p>
            )
          }
        />
      </div>
    </div>
  );
}
