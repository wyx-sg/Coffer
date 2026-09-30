// frontend/src/pages/AgentMemoryStorePage.tsx — spec agent-registry
// "Read one native memory store's files read-only".
// One of the agent's OWN native memory stores, reached from its row on the
// Memory tab (`/agents/<type>/memory/store?dir=&project=`): a file tree of the
// store directory and a read-only preview of the selected file, with
// open-in-editor / reveal on the file.
//
// The store is addressed by `?dir=` — the `memory_dir` the listing gave the row
// — because that directory IS the store's identity: the project label beside it
// is a best-effort decode, and for Codex several rows share one directory. The
// label rides along in `?project=` only for the heading.
//
// This surface never writes: the coding agent rewrites these bytes as it
// learns, so the way to change one is the editor the page opens.
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentMemoryStoreTree } from "@/components/agents/AgentMemoryStoreTree";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import { translateApiError } from "@/lib/api/errors";
import { countMemoryFiles, useNativeMemoryFiles } from "@/lib/hooks/useAgentNativeMemory";
import { useAgentRoute } from "@/lib/hooks/useAgentRoute";

export function AgentMemoryStorePage() {
  const { t } = useTranslation();
  const route = useAgentRoute();
  const params = useSearchParams()[0];
  const dir = params.get("dir") ?? "";
  const project = params.get("project");
  const tree = useNativeMemoryFiles(route.uid, dir);

  const type = route.type ?? "";
  const agentName = agentTypeLabel(type);
  const back = {
    to: agentTabPath(type, "memory"),
    label: t("agents.memoryStore.back", { agent: agentName }),
  };

  if (route.isPending) {
    return <PageHeader back={back} title={t("common.loading")} />;
  }
  if (!dir || route.notAdded || route.error) {
    const reason = !dir
      ? t("agents.memoryStore.missingDir")
      : route.error
        ? translateApiError(t, route.error)
        : t("agents.memoryStore.notAdded", { agent: agentName });
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={t("agents.memoryStore.unavailable")} />
        <EmptyState tone="error" title={t("agents.memoryStore.unavailable")} description={reason} />
      </div>
    );
  }

  const root = tree.data?.root;
  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={project ? abbreviateHomePath(project) : abbreviateHomePath(dir)}
        subtitle={
          root
            ? t("agents.memoryStore.subtitle", { agent: agentName, count: countMemoryFiles(root) })
            : t("agents.memoryStore.subtitleNoCount", { agent: agentName })
        }
      />
      <AgentMemoryStoreTree agentUid={route.uid} dir={dir} agentName={agentName} />
    </div>
  );
}
