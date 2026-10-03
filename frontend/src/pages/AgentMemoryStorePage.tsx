// frontend/src/pages/AgentMemoryStorePage.tsx — spec agent-registry
// "Read one native memory store's files read-only".
// One of the agent's OWN native memory stores, reached from its row on the
// Memory tab (`/agents/<type>/memory/store?dir=&project=`): the standard detail
// header (the agent's mark, the project, "<agent> memory · N files · read-only",
// Reveal in Finder) over one surface — the store's file tree beside a read-only
// viewer of the selected file (boards 2.1.51, 2.1.61).
//
// The store is addressed by `?dir=` — the `memory_dir` the listing gave the row
// — because that directory IS the store's identity: the project label beside it
// is a best-effort decode, and for Codex several rows share one directory. The
// label rides along in `?project=` only for the heading.
//
// This surface never writes: the coding agent rewrites these bytes as it
// learns, so the way to change one is the editor the viewer opens.
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { AgentMemoryStoreTree } from "@/components/agents/AgentMemoryStoreTree";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import { useFsActions } from "@/lib/fsActions";
import { countMemoryFiles, useNativeMemoryFiles } from "@/lib/hooks/useAgentNativeMemory";
import { useAgentRoute } from "@/lib/hooks/useAgentRoute";

export function AgentMemoryStorePage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  const route = useAgentRoute();
  const params = useSearchParams()[0];
  const dir = params.get("dir") ?? "";
  const project = params.get("project");
  const tree = useNativeMemoryFiles(route.uid, dir);

  const type = route.type ?? "";
  const agentName = agentTypeLabel(type);

  if (route.isPending) {
    return <PageHeader title={t("common.loading")} />;
  }
  if (!dir || route.notAdded || route.error) {
    const reason = !dir
      ? t("agents.memoryStore.missingDir")
      : route.error
        ? translateApiError(t, route.error)
        : t("agents.memoryStore.notAdded", { agent: agentName });
    return (
      <div className="space-y-6">
        <PageHeader title={t("agents.memoryStore.unavailable")} />
        <EmptyState tone="error" title={t("agents.memoryStore.unavailable")} description={reason} />
      </div>
    );
  }

  const root = tree.data?.root;
  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span className="inline-flex min-w-0 items-center gap-2.5">
            <AgentBadge type={type} size="lg" state="connected" tooltip={false} />
            <span className="truncate">
              {project ? abbreviateHomePath(project) : abbreviateHomePath(dir)}
            </span>
          </span>
        }
        subtitle={
          root
            ? t("agents.memoryStore.subtitle", { agent: agentName, count: countMemoryFiles(root) })
            : t("agents.memoryStore.subtitleNoCount", { agent: agentName })
        }
        actions={
          <Button
            variant="outline"
            onClick={() => void reveal(dir).catch(() => toast.error(t("fileActions.revealFailed")))}
          >
            <FolderOpen aria-hidden /> {t("fileActions.reveal")}
          </Button>
        }
      />
      <AgentMemoryStoreTree agentUid={route.uid} dir={dir} />
    </div>
  );
}
