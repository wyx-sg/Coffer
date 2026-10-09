// frontend/src/pages/KnowledgePage.tsx — the one Knowledge surface.
//
// A wiki app (spec knowledge "Show a collection as one tree of read-only
// documents in the web UI"): the tree of every collection on the left, each
// with its pages and sources, and whatever the address names on the right
// (lib/knowledge/routes.ts): a line to pick a collection, a collection, or an
// open file, read-only, with its history drawer when the address names it. Every collection is served to every agent, so
// there is no per-collection switch and no reach control; and the layer has no
// retrieval, so there is no search box — ⌘K jumps to a collection by name.
//
// New knowledge goes in as a source — an upload, an agent's file — and a
// person changes a page in their own editor (Open in editor). Tidying is the
// agent's: Tidy all hands every collection to the default managed agent and
// sends the prompt at once (spec knowledge "Hand a tidy to the agent").
//
// Nothing auto-provisions a collection, so an empty list is the first-run
// empty state. The page is a workspace (boards 5.1.01–5.1.29): a header — the
// title with its Experimental tag, one subtitle line, and on the right Tidy all
// and Upload, the page's one primary button — then the tree and the pane, each
// scrolling on its own.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";

import { ListLoadError } from "@/components/ListPaneStates";
import { KnowledgeDialogs, type KnowledgeDialog } from "@/components/knowledge/KnowledgeDialogs";
import { KnowledgeNav } from "@/components/knowledge/KnowledgeNav";
import { KnowledgePane } from "@/components/knowledge/KnowledgePane";
import { KnowledgeWelcomePanel } from "@/components/knowledge/KnowledgeWelcomePanel";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { ExperimentalTag } from "@/components/ExperimentalTag";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { Button } from "@/components/ui/button";
import { getTidyHandoff } from "@/lib/api/knowledge";
import { knowledgeKey } from "@/lib/api/queryKeys";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { legacyRedirect } from "@/lib/knowledge/routes";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { cn } from "@/lib/utils";

/** Tidy all's prompt, asked of the daemon when the button is pressed. */
const tidyAllPrompt = () => getTidyHandoff().then((handoff) => handoff.prompt);

export function KnowledgePage() {
  const { t } = useTranslation();
  // Agents write documents while the page is open: a knowledge change event
  // refetches everything read under knowledgeKey — the tree, document
  // bodies — without a poll.
  const qc = useQueryClient();
  useDaemonEvents({
    onMessage: (m) => {
      if (m.type === "change" && m.change.kind === "knowledge") {
        void qc.invalidateQueries({ queryKey: knowledgeKey });
      }
    },
  });
  const { uid, tab } = useParams<{ uid?: string; tab?: string }>();
  const { search } = useLocation();
  const [params] = useSearchParams();
  const file = params.get("file");
  const collections = useKnowledgeCollections();
  const [dialog, setDialog] = useState<KnowledgeDialog>(null);

  // A file's pane has no tabs: the History tab's old address
  // (`/<uid>/history?file=`) opens its history drawer, any other segment the
  // bare address.
  if (uid && tab) {
    return <Navigate to={legacyRedirect(uid, tab, search)} replace />;
  }

  const list = collections.data ?? [];
  const current = uid ? (list.find((c) => c.uid === uid) ?? null) : null;
  const empty = !collections.isPending && !collections.error && list.length === 0;
  const close = (open: boolean) => {
    if (!open) setDialog(null);
  };

  const header = (
    <div className={cn(PAGE_BLEED_HEAD, "shrink-0 pb-3")}>
      <PageHeader
        title={t("knowledge.title")}
        badges={<ExperimentalTag />}
        subtitle={t("knowledge.subtitle")}
        actions={
          list.length > 0 ? (
            <>
              <AgentHandoff prompt={tidyAllPrompt} label={t("knowledge.tidy.all")} help={false} />
              <Button onClick={() => setDialog("upload")}>
                <Upload aria-hidden /> {t("knowledge.upload.button")}
              </Button>
            </>
          ) : null
        }
      />
    </div>
  );

  const dialogs = (
    <KnowledgeDialogs
      dialog={dialog}
      onOpenChange={close}
      collections={list}
      initial={current?.name ?? null}
    />
  );

  // Full-bleed like Skills: Layout pads every page, and this one is a
  // workspace whose panes each scroll on their own.
  const shell = cn(PAGE_BLEED, "flex-col");

  if (empty) {
    return (
      <div className={shell}>
        {header}
        <div className="min-h-0 flex-1 overflow-auto">
          <KnowledgeWelcomePanel onCreate={() => setDialog("create")} />
        </div>
        {dialogs}
      </div>
    );
  }

  return (
    <div className={shell}>
      {header}
      <SplitView
        storageKey="knowledge"
        label={t("splitView.resizeList")}
        defaultListWidth={260}
        className="min-h-0 flex-1"
        listClassName="flex min-h-0 flex-col bg-surface-sidebar"
        detailClassName="flex min-h-0 min-w-0 flex-col"
        list={
          collections.error ? (
            // Unreadable: the tree pane says so under the header, the right pane stays empty.
            <ListLoadError
              kind="knowledge"
              error={collections.error}
              onRetry={() => void collections.refetch()}
            />
          ) : (
            <KnowledgeNav
              collections={list}
              isLoading={collections.isPending}
              currentUid={uid ?? null}
              file={file}
              onCreate={() => setDialog("create")}
            />
          )
        }
        detail={
          collections.error ? null : (
            <KnowledgePane
              uid={uid ?? null}
              collection={current}
              collectionsLoading={collections.isPending}
              file={file}
            />
          )
        }
      />
      {dialogs}
    </div>
  );
}
