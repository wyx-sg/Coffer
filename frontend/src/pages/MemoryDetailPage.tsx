// frontend/src/pages/MemoryDetailPage.tsx
//
// Detail surface for ONE partition: the folder it is on disk, plus the two
// acts that belong to the partition as a whole — where it reaches
// (ScopeControl) and the organise pass.
//
// Everything a reader could once do to an individual fact — hide, pin, settle
// a conflict, mark one superseded — is gone, along with the overrides that
// backed it. Those decisions only ever described Coffer's own derived copy,
// which aggregation rewrites from the agents' native memory on its own
// schedule; a verdict recorded against something regenerated behind your back
// is a promise the surface could not keep. What is left is the truth it can
// keep: here are the files, this is what they say, open one if you want to
// change it.
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useResource } from "@/lib/hooks/useResources";
import { MemoryFileTree } from "@/components/memory/MemoryFileTree";
import { useMemoryPartitions, useOrganisePartition } from "@/lib/hooks/useMemory";
import { useUpkeepRunning } from "@/lib/hooks/useUpkeep";

export function MemoryDetailPage() {
  const { t } = useTranslation();
  const partition = useParams<{ name: string }>().name ?? "";

  // `enabled` is a generic Resource field (not on the dedicated partitions
  // endpoint), so ScopeControl's required prop comes from the single-resource
  // read; `project_root` DOES live on the dedicated endpoint, so that is read
  // from there rather than reaching into the resource's untyped `config`.
  const resource = useResource("memory", partition);
  const partitions = useMemoryPartitions();
  const projectRoot = partitions.data?.find((p) => p.name === partition)?.project_root;
  const organise = useOrganisePartition(partition);
  // Whether a pass is running is the DAEMON's answer, not this component's:
  // the mutation's own `isPending` dies with the component, so leaving the
  // page mid-pass and coming back used to show an idle button and invite a
  // second concurrent pass over the same files. The local pending state is
  // still OR-ed in, because it covers the moment between the click and the
  // first poll.
  const passRunning = useUpkeepRunning("memory", partition);
  const organising = organise.isPending || passRunning;

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: "/memory", label: t("common.backTo", { label: t("nav.memory") }) }}
        title={partition}
        subtitle={projectRoot ? <span className="font-mono text-xs">{projectRoot}</span> : null}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ScopeControl kind="memory" name={partition} enabled={resource.data?.enabled ?? true} />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => organise.mutate()}
                  disabled={organising}
                >
                  <RefreshCw
                    className={organising ? "mr-1.5 size-3.5 animate-spin" : "mr-1.5 size-3.5"}
                  />
                  {t("memory.detail.organise")}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t("memory.detail.organiseHint")}</TooltipContent>
            </Tooltip>
          </div>
        }
      />

      <MemoryFileTree name={partition} />
    </div>
  );
}
