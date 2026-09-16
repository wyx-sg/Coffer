// frontend/src/pages/AgentMemoryStorePage.tsx — spec agent-registry/codex FR-012.
// One of the agent's OWN native memory stores, reached by clicking its row on
// the Memory tab: a file tree of the store directory and a read-only preview of
// the selected file, with open-in-editor / reveal on the file.
//
// The store is addressed by `?dir=` — the `memory_dir` the listing gave the row
// — because that directory IS the store's identity. The project label and path
// beside it are best-effort decodes of a lossy slug, and for Codex several rows
// legitimately share one global directory; keying the page by either would make
// two different stores collide or one store unreachable. The label still rides
// along in `?project=` for the heading, since a heading reading
// `/Users/u/.claude/projects/-Users-u-work-api/memory` tells the reader nothing
// they came here to learn.
//
// This surface never writes. Coffer does not own these bytes — the coding agent
// rewrites them as it learns — so the way to change one is the editor the page
// opens, not a field on the page.
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentMemoryStoreTree } from "@/components/agents/AgentMemoryStoreTree";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";

export function AgentMemoryStorePage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const params = useSearchParams()[0];
  const dir = params.get("dir") ?? "";
  const project = params.get("project");

  const back = {
    to: `/agents/${encodeURIComponent(name)}?tab=memory`,
    label: t("common.backTo", { label: t("agents.workspace.memory") }),
  };

  if (!dir) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={name} />
        <Card className="border-destructive/40">
          <CardContent className="py-6">
            <p className="text-sm text-destructive" role="alert">
              {t("agents.memoryStore.missingDir")}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={project || dir}
        subtitle={
          <>
            <span className="block break-all font-mono text-xs">{dir}</span>
            <span className="block">{t("agents.memoryStore.readOnlyHint")}</span>
          </>
        }
      />

      <AgentMemoryStoreTree name={name} dir={dir} />
    </div>
  );
}
