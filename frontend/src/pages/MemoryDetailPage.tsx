// frontend/src/pages/MemoryDetailPage.tsx
//
// Detail surface for ONE partition: the folder it is on disk, plus the two
// acts that belong to the partition as a whole — whether it is served at all
// (ScopeControl) and the distil pass.
//
// There is no per-agent reach here, and nothing on this page arranges that:
// the control passes no `scope`, so it asks the server, and the `memory` kind
// answers `supports_scope: false` — one enable/disable choice, no agent list.
// Memory is aggregated from every agent's own notes and served back to every
// agent; an enabled partition reaches all of them and a disabled one reaches
// nobody.
//
// Nothing here acts on an individual note, and that is the rule rather than an
// omission (FR-037). A partition is a folder of derived Markdown: `MEMORY.md`,
// `notes/`, `RETIRED.md`, and the `.raw/` those were distilled from. Coffer's
// own passes rewrite all of it on their own schedule, so a verdict recorded
// against one note — hide it, pin it, mark it dead — would be a promise the
// surface could not keep. What is left is the truth it can keep: here are the
// files, this is what they say, open one if you want to change it.
//
// The header names the REPOSITORY the partition is keyed on, not a working
// directory: a worktree and a second clone are one partition (FR-014). When
// that repository is gone from disk the header says so, because such a
// partition is delivered to nobody and only the developer can decide whether
// it should still exist (FR-016).
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useResource } from "@/lib/hooks/useResources";
import { MemoryFileTree } from "@/components/memory/MemoryFileTree";
import { useDistilPartition, useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useUpkeepRunning } from "@/lib/hooks/useUpkeep";

export function MemoryDetailPage() {
  const { t } = useTranslation();
  const uid = useParams<{ uid: string }>().uid ?? "";

  // `enabled` is a generic Resource field (not on the dedicated partitions
  // endpoint), so ScopeControl's required prop comes from the single-resource
  // read — the only reach state this kind has; the repository path and whether it still resolves DO live on the
  // dedicated endpoint, so those are read from there rather than reaching into
  // the resource's untyped `config`.
  const resource = useResource(uid);
  const partitions = useMemoryPartitions();
  const row = partitions.data?.find((p) => p.uid === uid);
  // The partition's LABEL, which is what the heading and the upkeep run list
  // both speak. Either read answers it; the resource read is the one that is
  // certain to be about this uid.
  const partition = resource.data?.name ?? row?.name ?? "";
  const distil = useDistilPartition(uid);
  // Whether a pass is running is the DAEMON's answer, not this component's:
  // the mutation's own `isPending` dies with the component, so leaving the
  // page mid-pass and coming back used to show an idle button and invite a
  // second concurrent pass over the same files. The local pending state is
  // still OR-ed in, because it covers the moment between the click and the
  // first poll.
  // Matched by NAME because that is what a run reports: `/upkeep/runs` names
  // the folder being rewritten, and the folder is named after the partition.
  const passRunning = useUpkeepRunning("memory", partition);
  const distilling = distil.isPending || passRunning;

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
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ScopeControl kind="memory" uid={uid} enabled={resource.data?.enabled ?? true} />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => distil.mutate()}
                  disabled={distilling}
                >
                  <RefreshCw
                    className={distilling ? "mr-1.5 size-3.5 animate-spin" : "mr-1.5 size-3.5"}
                  />
                  {t("memory.detail.distil")}
                </Button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">{t("memory.detail.distilHint")}</TooltipContent>
            </Tooltip>
          </div>
        }
      />

      <MemoryFileTree uid={uid} />
    </div>
  );
}
