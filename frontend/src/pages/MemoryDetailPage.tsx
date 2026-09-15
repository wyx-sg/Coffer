// frontend/src/pages/MemoryDetailPage.tsx
//
// Detail surface for ONE partition: its facts, conflicts as pairs to settle,
// and the organise action. Reach (ScopeControl) lives in the header, exactly
// as every other scoped Resource's detail page carries it.
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { translateApiError } from "@/lib/api/errors";
import { useResource } from "@/lib/hooks/useResources";
import { MemoryConflictsPanel } from "@/components/memory/MemoryConflictsPanel";
import { MemoryFactList } from "@/components/memory/MemoryFactList";
import {
  useMemoryFacts,
  useMemoryOverrides,
  useMemoryPartitions,
  useOrganisePartition,
} from "@/lib/hooks/useMemory";

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
  const facts = useMemoryFacts(partition);
  const overrides = useMemoryOverrides();
  const organise = useOrganisePartition(partition);

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
                  disabled={organise.isPending}
                >
                  <RefreshCw
                    className={
                      organise.isPending ? "mr-1.5 size-3.5 animate-spin" : "mr-1.5 size-3.5"
                    }
                  />
                  {t("memory.detail.organise")}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t("memory.detail.organiseHint")}</TooltipContent>
            </Tooltip>
          </div>
        }
      />

      {facts.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : facts.error ? (
        <Card>
          <CardContent className="py-8 text-center text-destructive">
            {translateApiError(t, facts.error)}
          </CardContent>
        </Card>
      ) : (
        <>
          <MemoryConflictsPanel facts={facts.data ?? []} overrides={overrides.data ?? []} />
          <MemoryFactList
            partition={partition}
            facts={facts.data ?? []}
            overrides={overrides.data ?? []}
          />
        </>
      )}
    </div>
  );
}
