// frontend/src/kinds/knowledge/KnowledgeDetailPage.tsx
//
// Detail surface for ONE knowledge scope — the single page the two former
// detail pages (memory store / knowledge base) collapse into. A back link +
// header (scope badge, both lanes' counts, settings / check-sources / reindex /
// upload), then a Tabs shell over the scope's material:
//
//   Entries    — what an agent wrote with `coffer__write` (`<scope>/knowledge/`)
//   Documents  — files someone ingested and Coffer converted (`<scope>/inbox/`)
//   Rules      — the single curated rules doc
//   Handoff    — per-branch scene notes
//   Changelog  — the consolidation log (a view, not a lane)
//
// Entries and documents are separate lanes with separate counts; each owns its
// own retrieval bar. Every body renders through the unified file preview —
// never a hand-styled <pre>. The UI is read-only for humans (correct a file in
// your own editor, or delete it); agents author entries over the MCP gateway.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getScope, getScopeMetrics } from "./api";
import { KnowledgeDetailHeader } from "./KnowledgeDetailHeader";
import { KnowledgeRenameDialog } from "./KnowledgeRenameDialog";
import { KnowledgeSettingsDialog } from "./KnowledgeSettingsDialog";
import { KnowledgeEntriesLane } from "./KnowledgeEntriesLane";
import { KnowledgeDocumentsLane } from "./KnowledgeDocumentsLane";
import { KnowledgeRulesLane } from "./KnowledgeRulesLane";
import { KnowledgeHandoffLane } from "./KnowledgeHandoffLane";
import { KnowledgeChangelogLane } from "./KnowledgeChangelogLane";
import { SourceCheckDialog } from "./SourceCheckDialog";
import { useKnowledgeDocuments } from "./useKnowledgeDocuments";

export function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const scope = useParams<{ scope: string }>().scope ?? "";
  const docs = useKnowledgeDocuments(scope);

  const [renameOpen, setRenameOpen] = useState(false);

  const metricsQuery = useQuery({
    queryKey: ["knowledge-metrics", scope],
    queryFn: () => getScopeMetrics(scope),
    enabled: Boolean(scope),
  });
  const scopeQuery = useQuery({
    queryKey: ["knowledge-scope", scope],
    queryFn: () => getScope(scope),
    enabled: Boolean(scope),
  });

  const onCheckSources = () =>
    docs.checkSources.mutate(undefined, {
      onError: (e) => toast.error(translateApiError(t, e)),
    });
  const onUpdateFromSource = (id: string) =>
    docs.updateFromSource.mutate(id, {
      onSuccess: () => toast.success(t("knowledge.detail.sourceCheck.updated")),
      // The edited-refusal (and any other failure) surfaces as a toast.
      onError: (e) => toast.error(translateApiError(t, e)),
    });

  return (
    <div className="space-y-6 p-6">
      <KnowledgeDetailHeader
        scope={scope}
        scopeResource={scopeQuery.data}
        metrics={metricsQuery.data}
        isReindexPending={docs.reindex.isPending}
        isUploadPending={docs.ingest.isPending}
        checkingSources={docs.checkSources.isPending}
        onRename={() => setRenameOpen(true)}
        onOpenSettings={() => docs.setShowSettings(true)}
        onCheckSources={onCheckSources}
        onReindex={() => docs.reindex.mutate()}
        onUpload={docs.handlePickFile}
      />

      {metricsQuery.error ? (
        <p className="text-sm text-destructive" role="alert">
          {translateApiError(t, metricsQuery.error)}
        </p>
      ) : null}

      <Tabs defaultValue="entries">
        <TabsList>
          <TabsTrigger value="entries">{t("knowledge.detail.tabs.entries")}</TabsTrigger>
          <TabsTrigger value="documents">{t("knowledge.detail.tabs.documents")}</TabsTrigger>
          <TabsTrigger value="rules">{t("knowledge.detail.tabs.rules")}</TabsTrigger>
          <TabsTrigger value="handoff">{t("knowledge.detail.tabs.handoff")}</TabsTrigger>
          <TabsTrigger value="changelog">{t("knowledge.detail.tabs.changelog")}</TabsTrigger>
        </TabsList>

        <TabsContent value="entries" className="pt-4">
          <KnowledgeEntriesLane scope={scope} scopeResource={scopeQuery.data} />
        </TabsContent>
        <TabsContent value="documents" className="pt-4">
          <KnowledgeDocumentsLane docs={docs} />
        </TabsContent>
        <TabsContent value="rules" className="pt-4">
          <KnowledgeRulesLane scope={scope} />
        </TabsContent>
        <TabsContent value="handoff" className="pt-4">
          <KnowledgeHandoffLane scope={scope} />
        </TabsContent>
        <TabsContent value="changelog" className="pt-4">
          <KnowledgeChangelogLane scope={scope} />
        </TabsContent>
      </Tabs>

      <input
        ref={docs.fileInputRef}
        type="file"
        className="hidden"
        onChange={docs.handleFileChange}
      />

      {docs.showSettings && scopeQuery.data ? (
        <KnowledgeSettingsDialog
          open
          onOpenChange={(o) => {
            if (!o) docs.updateConfig.reset();
            docs.setShowSettings(o);
          }}
          config={scopeQuery.data.config}
          error={docs.updateConfig.error}
          isPending={docs.updateConfig.isPending}
          onSubmit={(patch) => docs.updateConfig.mutate(patch)}
        />
      ) : null}

      {docs.sourceReport ? (
        <SourceCheckDialog
          open
          onOpenChange={(o) => {
            if (!o) docs.setSourceReport(null);
          }}
          report={docs.sourceReport}
          updatingId={docs.updateFromSource.isPending ? docs.updateFromSource.variables : null}
          onUpdate={onUpdateFromSource}
        />
      ) : null}

      <KnowledgeRenameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        scope={scope}
        currentLabel={scopeQuery.data?.label ?? null}
      />
    </div>
  );
}
