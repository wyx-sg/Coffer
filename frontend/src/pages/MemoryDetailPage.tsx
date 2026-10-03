// frontend/src/pages/MemoryDetailPage.tsx — one partition, at /memory/<uid>[/delivered]
// (spec memory "Present a partition as its memories").
//
// The header names the partition (its title when set), the repository it is
// keyed on — a worktree and a second clone are one partition ("Identify a
// partition by its repository") — and how many memories it holds; a partition
// whose repository is gone says so ("Report unresolvable partitions"). Its
// actions: Update memory (spinning while the daemon reports a distil pass over
// THIS partition, by uid, so leaving mid-pass and coming back still reads
// busy), the title editor and the ⋯ menu.
//
// Two tabs in the path: Memories (default) and Delivered. There is no status
// or reach control — every partition is served to every agent — and no
// per-memory action: memories are derived by distillation.
import { Brain } from "lucide-react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DetailNotFound } from "@/components/DetailNotFound";
import { PartitionDeliveredTab } from "@/components/memory/PartitionDeliveredTab";
import { PartitionMemoriesTab } from "@/components/memory/PartitionMemoriesTab";
import { PartitionMenu } from "@/components/memory/PartitionMenu";
import { MemoryAutomaticPopover } from "@/components/memory/MemoryAutomaticPopover";
import { useMemoryUpdateRunning } from "@/components/memory/MemoryHeaderStatus";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { distilState } from "@/components/memory/partitionFacts";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { PageHeader } from "@/components/PageHeader";
import { EditTitleDialog } from "@/components/resource/EditTitleDialog";
import { ResourceLabel } from "@/components/resource/ResourceLabel";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useDetailTab } from "@/lib/detailTabs";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useUpkeepRunning } from "@/lib/hooks/useUpkeep";
import { displayName } from "@/lib/resourceTitle";

const MEMORY_TABS = ["memories", "delivered"] as const;

export function MemoryDetailPage() {
  const { t, i18n } = useTranslation();
  const uid = useParams<{ uid: string }>().uid ?? "";
  const partitions = useMemoryPartitions();
  const row = partitions.data?.find((p) => p.uid === uid);
  const distilling = useUpkeepRunning("memory", uid);
  const updating = useMemoryUpdateRunning();
  const running = distilling || updating;
  const [tab, setTab] = useDetailTab(MEMORY_TABS, "memories", `/memory/${encodeURIComponent(uid)}`);

  if (partitions.isPending) {
    return (
      <div className="space-y-6" aria-busy="true">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-8 w-64" />
      </div>
    );
  }
  if (!row) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("memory.title")} />
        <DetailNotFound kind="memory" id={uid} backTo="/memory" icon={Brain} />
      </div>
    );
  }

  const subtitle = [
    row.repository_path ? abbreviateHomePath(row.repository_path) : t("memory.cols.global"),
    t("memory.partitions.memories", { count: row.note_count }),
    distilState(t, i18n.language, row, distilling).toLowerCase(),
  ].join(" · ");

  return (
    <div className="flex min-h-0 flex-col gap-4">
      <PageHeader
        title={<ResourceLabel resource={row} heading />}
        badges={row.unresolvable ? <UnresolvableBadge /> : null}
        subtitle={subtitle}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <MemoryAutomaticPopover />
            <MemoryUpdateButton variant="outline" size="sm" running={running} />
            {/* Not on the boards; kept because a partition's editable title is
                still required (spec resource-framework). */}
            <EditTitleDialog kind="memory" resource={row} />
            <PartitionMenu partition={row} />
          </div>
        }
      />

      <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-col">
        <TabsList>
          <TabsTrigger value="memories">{t("memory.detail.tabs.memories")}</TabsTrigger>
          <TabsTrigger value="delivered">{t("memory.detail.tabs.delivered")}</TabsTrigger>
        </TabsList>
        <TabsContent value={tab} className="mt-[18px] min-h-0">
          {tab === "memories" ? (
            <PartitionMemoriesTab
              uid={uid}
              name={displayName(row)}
              running={running}
              partition={row}
            />
          ) : (
            <PartitionDeliveredTab uid={uid} repositoryPath={row.repository_path} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
