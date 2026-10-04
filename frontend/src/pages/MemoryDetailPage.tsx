// frontend/src/pages/MemoryDetailPage.tsx — one partition, at /memory/<uid>[/delivered]
// (spec memory "Present a partition as its memories").
//
// The header is the partition's name alone (no back link, no Experimental tag,
// no Automatic control) over one description line: the repository it is keyed
// on in mono — a worktree and a second clone are one partition ("Identify a
// partition by its repository") — how many memories it holds and when it was
// distilled; a partition whose repository is gone says so ("Report
// unresolvable partitions"). Its actions: Tidy (hands the partition to the
// default managed agent and sends the prompt at once; spec memory "Hand a
// partition's tidying to the agent"), Update memory, secondary (spinning while
// the daemon reports a distil pass over THIS partition, by uid, so leaving
// mid-pass and coming back still reads busy) and the ⋯ menu. Boards
// 5.2.06–5.2.09.
//
// Two tabs in the path: Memories (default) and Delivered. There is no status
// or reach control — every partition is served to every agent — and no
// per-memory action but Edit: memories are derived by distillation, and
// a person's edit is the memory until newer evidence revises it.
import { Brain } from "lucide-react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DetailNotFound } from "@/components/DetailNotFound";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { PartitionDeliveredTab } from "@/components/memory/PartitionDeliveredTab";
import { PartitionMemoriesTab } from "@/components/memory/PartitionMemoriesTab";
import { PartitionMenu } from "@/components/memory/PartitionMenu";
import { useMemoryUpdateRunning } from "@/components/memory/MemoryHeaderStatus";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { distilState } from "@/components/memory/partitionFacts";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useDetailTab } from "@/lib/detailTabs";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useUpkeepRunning } from "@/lib/hooks/useUpkeep";

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

  const where = row.repository_path ? (
    <span className="font-mono text-xs">{abbreviateHomePath(row.repository_path)}</span>
  ) : (
    t("memory.cols.global")
  );
  const subtitle = (
    <span className="text-text-muted">
      {where} · {t("memory.partitions.memories", { count: row.note_count })} ·{" "}
      {distilState(t, i18n.language, row, distilling).toLowerCase()}
    </span>
  );

  return (
    <div className="flex min-h-0 flex-col gap-4">
      <PageHeader
        title={row.name}
        badges={row.unresolvable ? <UnresolvableBadge /> : null}
        subtitle={subtitle}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <AgentHandoff
              prompt={row.tidy_handoff.prompt}
              autoSend={{ label: t("memory.tidy.one") }}
              help={false}
            />
            <MemoryUpdateButton variant="outline" running={running} />
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
            <PartitionMemoriesTab uid={uid} name={row.name} partition={row} />
          ) : (
            <PartitionDeliveredTab uid={uid} repositoryPath={row.repository_path} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
