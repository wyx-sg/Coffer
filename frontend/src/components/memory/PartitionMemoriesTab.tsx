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
// original text. A memory's own actions (Edit, Open in editor, Reveal, Delete…)
// sit on the pane beside the list. A partition not distilled yet has no list column at all:
// only the centred empty state, with no Update memory button (the header has
// it; board 5.2.08).
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";
import { Brain } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { FILE_PANE_COLUMN, useFillToBottom } from "@/components/filePane";
import { MemoryList, RetiredGroup } from "@/components/memory/MemoryList";
import { MemoryPane } from "@/components/memory/MemoryPane";
import { RetiredPane } from "@/components/memory/RetiredPane";
import { NoModelNotice } from "@/components/memory/NoModelNotice";
import { SplitView } from "@/components/SplitView";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { agentTypeLabel } from "@/lib/agents/display";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { agentTypeOfOrigin } from "./memoryAgents";
import { useCofferModelSet } from "@/lib/hooks/useInternalEngine";
import { useMemoryNotes, useMemoryRetired } from "@/lib/hooks/useMemory";

/** The search param naming the selected memory. */
const MEMORY_PARAM = "memory";
/** The search param naming the selected retired memory, by its index in
 *  RETIRED.md's order (a slug can be empty: an entry that never became a note). */
const RETIRED_PARAM = "retired";

interface Props {
  uid: string;
  /** The partition's display name, for the empty state. */
  name: string;
  /** The partition's row: its sources decide "All agents", and entries read
   *  but not distilled yet are what an empty list says it is waiting on. */
  partition?: PartitionOut;
}

export function PartitionMemoriesTab({ uid, name, partition }: Props) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const notes = useMemoryNotes(uid);
  const retired = useMemoryRetired(uid);
  const modelSet = useCofferModelSet();
  const fill = useFillToBottom();

  const memories = notes.data ?? [];
  const wanted = params.get(MEMORY_PARAM);
  const retiredList = retired.data ?? [];
  const wantedRetired = params.get(RETIRED_PARAM);
  const retiredIndex =
    wantedRetired !== null && /^\d+$/.test(wantedRetired) ? Number(wantedRetired) : null;
  const selectedRetired =
    retiredIndex !== null && retiredIndex < retiredList.length ? retiredIndex : null;
  const selected =
    selectedRetired !== null
      ? null
      : (memories.find((m) => m.slug === wanted)?.slug ?? memories[0]?.slug ?? null);
  const select = (slug: string) => {
    const next = new URLSearchParams(params);
    next.set(MEMORY_PARAM, slug);
    next.delete(RETIRED_PARAM);
    setParams(next, { replace: true });
  };
  const selectRetired = (index: number) => {
    const next = new URLSearchParams(params);
    next.set(RETIRED_PARAM, String(index));
    setParams(next, { replace: true });
  };

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
        />
        {(retired.data ?? []).length > 0 ? <RetiredGroup retired={retired.data ?? []} /> : null}
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
            <div className="flex min-h-0 flex-1 flex-col">
              <MemoryList
                memories={memories}
                retired={retiredList}
                selected={selected}
                onSelect={select}
                selectedRetired={selectedRetired}
                onSelectRetired={selectRetired}
                sources={partition?.sources ?? []}
              />
            </div>
          }
          detail={
            selectedRetired !== null ? (
              <RetiredPane
                record={retiredList[selectedRetired]}
                memories={memories}
                onSelectMemory={select}
              />
            ) : selected ? (
              <MemoryPane uid={uid} slug={selected} partitionName={name} />
            ) : (
              <p className="text-sm text-text-muted">{t("memory.memories.select")}</p>
            )
          }
        />
      </div>
    </div>
  );
}
