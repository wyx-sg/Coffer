// frontend/src/pages/KnowledgePage.tsx — the one Knowledge surface.
//
// A document app (spec knowledge "Present a collection as one tree in the web
// UI"): the tree of every collection on the left — Recent changes on top, then
// each collection with its Inbox and its documents — and whatever the address
// names on the right (lib/knowledge/routes.ts): Recent changes, one change, a
// collection, an open document with its Document and History tabs, or the
// Inbox. Every collection is served to every agent, so there is no
// per-collection switch and no reach control; and the layer has no retrieval,
// so there is no search box — ⌘K jumps to a collection by name.
//
// New knowledge goes in as an ITEM — an upload, an agent's file in `.inbox/` —
// which waits in the collection's Inbox until curation files it into the right
// document; people write through Edit. With Coffer's engine not set there is
// nothing to curate with: the Automatic control reads "Curation needs Coffer's
// engine" (→ Settings › General) and there is no Inbox and no Curate now.
//
// Nothing auto-provisions a collection, so an empty list is the first-run
// empty state. The page is a workspace (boards 5.1.01–5.1.29): a header — the
// title with its Experimental tag, one subtitle line, and on the right the
// Automatic control and Upload, the page's one primary button (secondary while
// a document has unsaved edits) — then the tree and the pane, each scrolling
// on its own.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";

import { ListLoadError } from "@/components/ListPaneStates";
import { KnowledgeAutomaticPopover } from "@/components/knowledge/KnowledgeAutomaticPopover";
import { KnowledgeDialogs, type KnowledgeDialog } from "@/components/knowledge/KnowledgeDialogs";
import { KnowledgeNav } from "@/components/knowledge/KnowledgeNav";
import { KnowledgePane } from "@/components/knowledge/KnowledgePane";
import { KnowledgeWelcomePanel } from "@/components/knowledge/KnowledgeWelcomePanel";
import { ExperimentalTag } from "@/components/ExperimentalTag";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { Button } from "@/components/ui/button";
import { knowledgeKey } from "@/lib/api/queryKeys";
import { useDetailTab } from "@/lib/detailTabs";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { useCofferModelSet } from "@/lib/hooks/useInternalEngine";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useEditingDocument } from "@/lib/knowledge/dirtyDocument";
import { useOpenSettings } from "@/lib/settingsModal";
import {
  collectionBasePath,
  DEFAULT_KNOWLEDGE_TAB,
  KNOWLEDGE_ROOT,
  KNOWLEDGE_TABS,
} from "@/lib/knowledge/routes";

export function KnowledgePage() {
  const { t } = useTranslation();
  // Agents write items while the page is open: a knowledge change event
  // (submit, curation settling) refetches everything read under knowledgeKey —
  // Inbox counts, the tree, document bodies — without a poll.
  const qc = useQueryClient();
  useDaemonEvents({
    onMessage: (m) => {
      if (m.type === "change" && m.change.kind === "knowledge") {
        void qc.invalidateQueries({ queryKey: knowledgeKey });
      }
    },
  });
  const { uid, version } = useParams<{ uid?: string; version?: string }>();
  const [params] = useSearchParams();
  const file = params.get("file");
  const collections = useKnowledgeCollections();
  const modelSet = useCofferModelSet();
  const [dialog, setDialog] = useState<KnowledgeDialog>(null);
  const openSettings = useOpenSettings();
  // While a document has unsaved edits, Upload steps back to secondary.
  // (The editor publishes only its dirty state, so this is the signal we have.)
  const editing = useEditingDocument() !== null;

  const [tab] = useDetailTab(
    KNOWLEDGE_TABS,
    DEFAULT_KNOWLEDGE_TAB,
    uid ? collectionBasePath(uid) : KNOWLEDGE_ROOT,
    { enabled: Boolean(uid) },
  );

  const list = collections.data ?? [];
  const current = uid ? (list.find((c) => c.uid === uid) ?? null) : null;
  const empty = !collections.isPending && !collections.error && list.length === 0;
  const close = (open: boolean) => {
    if (!open) setDialog(null);
  };

  const header = (
    <div className="shrink-0 px-8 pb-3 pt-4">
      <PageHeader
        title={t("knowledge.title")}
        badges={<ExperimentalTag />}
        subtitle={t("knowledge.subtitle")}
        actions={
          list.length > 0 ? (
            <>
              {modelSet ? (
                <KnowledgeAutomaticPopover />
              ) : modelSet === false ? (
                <Button
                  type="button"
                  variant="link"
                  className="px-0"
                  onClick={() => openSettings("general")}
                >
                  {t("knowledge.noModel.engine")}
                </Button>
              ) : null}
              <Button variant={editing ? "outline" : "default"} onClick={() => setDialog("upload")}>
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
  const shell = "-mx-8 -mb-10 -mt-4 flex h-screen flex-col overflow-hidden";

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
              tab={tab}
              file={file}
              atRecent={!uid && !version}
              modelSet={modelSet}
              onCreate={() => setDialog("create")}
            />
          )
        }
        detail={
          collections.error ? null : (
            <KnowledgePane
              uid={uid ?? null}
              version={version ?? null}
              collection={current}
              collections={list}
              collectionsLoading={collections.isPending}
              tab={tab}
              file={file}
              modelSet={modelSet}
            />
          )
        }
      />
      {dialogs}
    </div>
  );
}
