// frontend/src/pages/KnowledgeDetailPage.tsx
//
// Detail surface for ONE collection, which is TWO trees rather than one (spec
// knowledge FR-040, ADR knowledge-is-plain-files):
//
//   sources/ — what the person and the agents wrote. Editable in the sense
//              this page has always meant: handed to the user's own editor,
//              revealed in their file manager, and deletable from here.
//   topics/  — what Coffer's curation derived from those sources. Opened and
//              revealed, never deleted and never edited: curation is the only
//              writer of that lane, so a correction goes in as a new source
//              and the next pass carries it through.
//
// Read-only is deliberate and load-bearing on BOTH lanes. Correcting a source
// happens in the user's own editor, reached from the FileActions bar on the
// preview; with no index behind the files, that edit is live on the very next
// read with nothing to reconcile.
//
// Reach (ScopeControl) lives in the header, as on every other scoped Resource's
// detail page: which agents this collection is exposed to is a property of the
// collection, not of the file open in the pane.
//
// The lane and the open file both live in the URL (`?tab=`, `?file=`), so a
// reload or a shared link comes back to the same document — addressable state
// belongs to the router (agents/frontend.md §3). Switching lanes clears the
// file: a path belongs to one lane, and the pane beside a tree shows what that
// tree holds.
//
// There is NO retrieval box anywhere on this page. The one input beside each
// tree narrows the names already on screen, client-side; the layer exposes no
// search and no grep at all, and an agent reads the files with its own tools at
// the paths its delivered skill carries (FR-050).
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { KnowledgeCurateButton } from "@/components/knowledge/KnowledgeCurateButton";
import { KnowledgeLane } from "@/components/knowledge/KnowledgeLane";
import { KnowledgeUploadButton } from "@/components/knowledge/KnowledgeUploadButton";
import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useResource } from "@/lib/hooks/useResources";
import { isKnowledgeLane, uploadFolderOf, type KnowledgeLane as Lane } from "@/lib/knowledge/lanes";

export function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const collection = useParams<{ name: string }>().name ?? "";
  const [params, setParams] = useSearchParams();

  const tab = params.get("tab");
  const lane: Lane = isKnowledgeLane(tab) ? tab : "sources";
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

  // Changing lane drops the open file: it belongs to the lane being left, and
  // previewing it beside the other lane's tree would offer a source's delete
  // under the Topics tab (or the reverse).
  const setLane = (next: string) =>
    setParams(
      (prev) => {
        if (next === "sources") prev.delete("tab");
        else prev.set("tab", next);
        prev.delete("file");
        return prev;
      },
      { replace: true },
    );

  // An upload lands where the user is: the folder of the source currently open,
  // or the `sources/` lane's own top level. Relative to that lane, matching
  // `IngestService`, and never derived from a topic path — an upload is a
  // source.
  const uploadFolder = uploadFolderOf(collection, selected);

  // `enabled` is a generic Resource field, not on /knowledge/collections, so
  // the reach control's required prop comes from the single-resource read.
  const resource = useResource("knowledge", collection);

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: "/knowledge", label: t("common.backTo", { label: t("nav.knowledge") }) }}
        title={collection}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* Reach sits in the header, exactly as every other kind's detail
                page carries it; passing no `scope` lets it fetch its own. */}
            <ScopeControl
              kind="knowledge"
              name={collection}
              enabled={resource.data?.enabled ?? true}
            />
            <KnowledgeCurateButton collection={collection} />
            <KnowledgeUploadButton collection={collection} folder={uploadFolder} />
          </div>
        }
      />

      <Tabs value={lane} onValueChange={setLane}>
        <TabsList>
          <TabsTrigger value="sources">{t("knowledge.detail.lanes.sources.tab")}</TabsTrigger>
          <TabsTrigger value="topics">{t("knowledge.detail.lanes.topics.tab")}</TabsTrigger>
        </TabsList>

        <TabsContent value="sources" className="pt-6">
          <KnowledgeLane
            collection={collection}
            lane="sources"
            selected={selected}
            onSelect={setSelected}
          />
        </TabsContent>

        <TabsContent value="topics" className="pt-6">
          <KnowledgeLane
            collection={collection}
            lane="topics"
            selected={selected}
            onSelect={setSelected}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
