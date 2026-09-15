// frontend/src/pages/MemoryDetailPage.tsx
//
// Detail surface for ONE partition: its facts, conflicts as pairs to settle,
// and the organise action. Reach (ScopeControl) lives in the header, exactly
// as every other scoped Resource's detail page carries it.
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  const navigate = useNavigate();

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
      {/* The way back to the list, as every other detail page carries it. A
          partition is reached by clicking a row, so leaving it must not depend
          on the browser's own back button. */}
      <div className="-ml-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/memory")}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1.5 size-4" />
          {t("common.backTo", { label: t("nav.memory") })}
        </Button>
      </div>

      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">{partition}</h1>
          {projectRoot ? (
            <p className="font-mono text-xs text-muted-foreground">{projectRoot}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ScopeControl kind="memory" name={partition} enabled={resource.data?.enabled ?? true} />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => organise.mutate()}
            disabled={organise.isPending}
          >
            <RefreshCw
              className={organise.isPending ? "mr-1.5 size-3.5 animate-spin" : "mr-1.5 size-3.5"}
            />
            {t("memory.detail.organise")}
          </Button>
        </div>
      </header>

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
