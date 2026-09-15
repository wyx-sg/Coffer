// frontend/src/pages/AgentMemoryStorePage.tsx — spec agent-registry FR-040.
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
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";

import { AgentMemoryStoreTree } from "@/components/agents/AgentMemoryStoreTree";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function AgentMemoryStorePage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const params = useSearchParams()[0];
  const dir = params.get("dir") ?? "";
  const project = params.get("project");

  const back = (
    <div className="-ml-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(`/agents/${encodeURIComponent(name)}?tab=memory`)}
        className="text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" />
        {t("common.backTo", { label: t("agents.workspace.memory") })}
      </Button>
    </div>
  );

  if (!dir) {
    return (
      <div className="space-y-6">
        {back}
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
      {back}

      <header className="space-y-1">
        <h1 className="font-serif text-2xl tracking-tight">{project || dir}</h1>
        <p className="break-all font-mono text-xs text-muted-foreground">{dir}</p>
        <p className="text-xs text-muted-foreground">{t("agents.memoryStore.readOnlyHint")}</p>
      </header>

      <AgentMemoryStoreTree name={name} dir={dir} />
    </div>
  );
}
