// frontend/src/pages/KnowledgeDetailPage.tsx
//
// Detail surface for ONE collection, which is ONE tree of Markdown documents
// (spec knowledge FR-040, ADR knowledge-is-plain-files). People and Coffer's
// curation write the same documents: a person edits one in their own editor
// (reached from the FileActions bar on the preview) or deletes it here, and a
// curation pass merges new material into them. There is no second tree of
// "what I wrote" beside "what Coffer derived" — knowledge is co-created, and a
// reader should find a fact in one place.
//
// New material — an upload, an agent's `coffer__write`, the CLI — does not
// land in the tree directly. It waits in the collection's hidden inbox until a
// pass merges it, so the page says how much is waiting: that is exactly the
// part of the collection an agent cannot read yet.
//
// Read-only is deliberate and load-bearing. Correcting a document happens in
// the user's own editor; with no index behind the files, that edit is live on
// the very next read with nothing to reconcile.
//
// Whether the collection is served at all (ScopeControl) lives in the header,
// where every other kind's detail page carries it: it is a property of the
// collection, not of the file open in the pane.
//
// It is one choice there, not a per-agent one, and nothing on this page
// arranges that: the control passes no `scope`, so it asks the server, and the
// `knowledge` kind answers `supports_scope: false` — enable or disable, no
// agent list. An enabled collection is named in every agent's delivered skill;
// a disabled one is named in none.
//
// The open file lives in the URL (`?file=`), so a reload or a shared link
// comes back to the same document — addressable state belongs to the router
// (agents/frontend.md §3).
//
// There is NO retrieval box anywhere on this page. The one input beside the
// tree narrows the names already on screen, client-side; the layer exposes no
// search and no grep at all, and an agent reads the files with its own tools at
// the paths its delivered skill carries (FR-050).
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Inbox } from "lucide-react";

import { KnowledgeBrowser } from "@/components/knowledge/KnowledgeBrowser";
import { KnowledgeCurateButton } from "@/components/knowledge/KnowledgeCurateButton";
import { KnowledgeUploadButton } from "@/components/knowledge/KnowledgeUploadButton";
import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useResource } from "@/lib/hooks/useResources";

export function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const uid = useParams<{ uid: string }>().uid ?? "";
  const [params, setParams] = useSearchParams();

  // `enabled` is a generic Resource field, not on /knowledge/collections, so
  // the control's required prop comes from the single-resource read — and it is
  // the only reach state this kind has. The same read supplies the collection's
  // NAME, which is what the file routes below need: a `path` names a place on
  // disk, and a collection's directory is named after it. So this page holds
  // both — the uid it is addressed by, and the name its tree is built from.
  const resource = useResource(uid);
  const collection = resource.data?.name ?? "";

  // The inbox count is read off disk, so it is on the collection list rather
  // than the Resource. Matched by uid: a rename between the two reads must not
  // lose it.
  const collections = useKnowledgeCollections();
  const pending = collections.data?.find((c) => c.uid === uid)?.pending_count ?? 0;

  const selected = params.get("file");
  const setSelected = (path: string | null) =>
    setParams(
      (prev) => {
        if (path) prev.set("file", path);
        else prev.delete("file");
        return prev;
      },
      { replace: true },
    );

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: "/knowledge", label: t("common.backTo", { label: t("nav.knowledge") }) }}
        title={collection}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* Passing no `scope` is what lets the control ask the server —
                which is where the "no per-agent reach" answer comes from. */}
            <ScopeControl kind="knowledge" uid={uid} enabled={resource.data?.enabled ?? true} />
            <KnowledgeCurateButton collectionUid={uid} collectionName={collection} />
            <KnowledgeUploadButton collection={collection} />
          </div>
        }
      />

      {pending > 0 ? (
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <Inbox className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>{t("knowledge.detail.pending", { count: pending })}</span>
        </p>
      ) : null}

      <KnowledgeBrowser collection={collection} selected={selected} onSelect={setSelected} />
    </div>
  );
}
