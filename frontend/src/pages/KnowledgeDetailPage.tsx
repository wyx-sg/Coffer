// frontend/src/pages/KnowledgeDetailPage.tsx
//
// Detail surface for ONE collection, which is ONE tree of Markdown documents
// (spec knowledge "Present a collection as one tree in the web UI", ADR
// knowledge-is-plain-files). People and Coffer's
// curation write the same documents: a person edits one in their own editor
// (reached from the FileActions bar on the preview) or deletes it here, and a
// curation pass merges new material into them. There is no second tree of
// "what I wrote" beside "what Coffer derived" — knowledge is co-created, and a
// reader should find a fact in one place.
//
// New material — an upload, an agent's `coffer__write`, the CLI — does not
// land in the documents directly. It waits in the collection's inbox until a
// pass merges it; the header's Curate button runs the next pass now.
//
// There is no status or reach control in the header: every collection is
// served to every agent (spec knowledge "Serve every collection to every
// agent"), so a control there would offer a choice with nothing behind it.
//
// The open file lives in the URL (`?file=`), so a reload or a shared link
// comes back to the same document — addressable state belongs to the router
// (agents/frontend.md §3).
//
// There is NO retrieval box anywhere on this page, and no filter over the
// tree: the layer exposes no search and no grep at all, and an agent reads the
// files with its own tools at the paths its delivered skill carries (see
// "Expose exactly one knowledge tool").
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { KnowledgeBrowser } from "@/components/knowledge/KnowledgeBrowser";
import { KnowledgeCurateButton } from "@/components/knowledge/KnowledgeCurateButton";
import { KnowledgeUploadButton } from "@/components/knowledge/KnowledgeUploadButton";
import { PageHeader } from "@/components/PageHeader";
import { useResource } from "@/lib/hooks/useResources";

export function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const uid = useParams<{ uid: string }>().uid ?? "";
  const [params, setParams] = useSearchParams();

  // The page is addressed by uid, but the file routes below need the
  // collection's NAME: a `path` names a place on disk, and a collection's
  // directory is named after it. The single-resource read supplies it.
  const resource = useResource(uid);
  const collection = resource.data?.name ?? "";

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
            <KnowledgeCurateButton collectionUid={uid} collectionName={collection} />
            <KnowledgeUploadButton collection={collection} />
          </div>
        }
      />

      <KnowledgeBrowser collection={collection} selected={selected} onSelect={setSelected} />
    </div>
  );
}
