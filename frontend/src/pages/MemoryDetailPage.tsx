// frontend/src/pages/MemoryDetailPage.tsx
//
// Detail surface for ONE partition: the folder it is on disk, plus the one act
// that belongs to memory as a whole — Update memory, the same button the
// partitions page carries (spec memory "Update memory in one action").
//
// There is no status or reach control here: every partition is served to every
// agent (spec memory "Serve every partition to every agent"), so a header
// control would offer a choice with nothing behind it.
//
// Nothing here acts on an individual note, and that is the rule rather than an
// omission (see "Present partitions as a table and a file tree"). A partition
// is a folder of derived Markdown: `MEMORY.md`, `notes/` and `RETIRED.md`.
// Coffer's own passes rewrite all of it on their own schedule, so a verdict
// recorded against one note — hide it, pin it, mark it dead — would be a
// promise the surface could not keep. What is left is the truth it can keep:
// here are the files, this is what they say, open one if you want to change it.
//
// The header names the REPOSITORY the partition is keyed on, not a working
// directory: a worktree and a second clone are one partition (see
// "Identify a partition by its repository"). When
// that repository is gone from disk the header says so, because such a
// partition is delivered to nobody and only the developer can decide whether
// it should still exist (see "Report unresolvable partitions").
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { MemoryFileTree } from "@/components/memory/MemoryFileTree";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useUpkeepRunning } from "@/lib/hooks/useUpkeep";

export function MemoryDetailPage() {
  const { t } = useTranslation();
  const uid = useParams<{ uid: string }>().uid ?? "";

  // The partition's label, repository path and whether it still resolves all
  // live on the dedicated endpoint, matched here by uid.
  const partitions = useMemoryPartitions();
  const row = partitions.data?.find((p) => p.uid === uid);
  const partition = row?.name ?? "";
  // Whether a distil pass over THIS partition is running is the DAEMON's
  // answer, not this component's: a pass outlives the page, so leaving mid-pass
  // and coming back must still show the button busy rather than invite a
  // second concurrent pass over the same files. Matched by NAME because that
  // is what a run reports: `/upkeep/runs` names the folder being rewritten,
  // and the folder is named after the partition.
  const passRunning = useUpkeepRunning("memory", partition);

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: "/memory", label: t("common.backTo", { label: t("nav.memory") }) }}
        title={partition}
        badges={row?.unresolvable ? <UnresolvableBadge /> : null}
        subtitle={
          row?.repository_path ? (
            <span className="font-mono text-xs">{row.repository_path}</span>
          ) : null
        }
        actions={<MemoryUpdateButton variant="outline" size="sm" running={passRunning} />}
      />

      <MemoryFileTree uid={uid} />
    </div>
  );
}
