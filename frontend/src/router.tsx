import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { Layout } from "./components/Layout";
import { PageFallback } from "./components/PageFallback";
import { AgentsPage } from "./pages/AgentsPage";
import { ChannelsPage } from "./pages/ChannelsPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { ModelProvidersPage } from "./pages/ModelProvidersPage";
import { NotFoundPage } from "./pages/NotFoundPage";

// Page-level code splitting. The list pages a user lands on stay in the main
// bundle so the first paint needs one request; every detail page and every
// surface that pulls in the editor, the highlighter or the markdown pipeline
// (chat, activity, settings, sync, knowledge, memory) is loaded on first
// visit. `lazy()` wants a default export and §6 forbids them, so the loader
// picks the named export out of the module.
function lazyPage<K extends string>(
  load: () => Promise<Record<K, ComponentType<object>>>,
  name: K,
): JSX.Element {
  const Page: LazyExoticComponent<ComponentType<object>> = lazy(() =>
    load().then((m) => ({ default: m[name] })),
  );
  return (
    <Suspense fallback={<PageFallback />}>
      <Page />
    </Suspense>
  );
}

// Exported as data, not only as a built router: a test that has to prove a
// legacy URL still lands somewhere (rather than on "page not found") needs the
// real route table under a memory router, and rebuilding it in the test would
// prove nothing about this one.
//
// Every detail route is `:uid` — a resource's immutable identity — and not its
// name. A name is a label the user edits, so a URL built from one stops
// resolving the moment they do, and the page it names would 404 while the thing
// it was about is still there (ADR resource-identity-is-an-immutable-uid).
// Nothing translates an old name-based URL into a uid one: doing so would need
// a lookup by name, which is the addressing this change removed.
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/agents" replace /> },
      { path: "chat", element: lazyPage(() => import("./pages/ChatPage"), "ChatPage") },
      { path: "chat/:id", element: lazyPage(() => import("./pages/ChatPage"), "ChatPage") },
      { path: "mcp-servers", element: <ResourcesPage /> },
      {
        path: "mcp-servers/:uid",
        element: lazyPage(() => import("./pages/ResourceDetailPage"), "ResourceDetailPage"),
      },
      // Legacy route — this surface used to live at /resources.
      { path: "resources", element: <Navigate to="/mcp-servers" replace /> },
      { path: "agents", element: <AgentsPage /> },
      {
        path: "agents/:uid",
        element: lazyPage(() => import("./pages/AgentDetailPage"), "AgentDetailPage"),
      },
      // Detail pages reached by clicking a row on the agent's Memory /
      // Conversations tabs. Each identifies its subject by a search param (the
      // store's `dir`, the session's `path`) rather than a path segment,
      // because both identities are absolute filesystem paths — a path segment
      // would have to survive encoding its own separators.
      {
        path: "agents/:uid/conversations",
        element: lazyPage(() => import("./pages/AgentConversationPage"), "AgentConversationPage"),
      },
      {
        path: "agents/:uid/memory",
        element: lazyPage(() => import("./pages/AgentMemoryStorePage"), "AgentMemoryStorePage"),
      },
      { path: "channels", element: <ChannelsPage /> },
      {
        path: "channels/:uid",
        element: lazyPage(() => import("./pages/ChannelDetailPage"), "ChannelDetailPage"),
      },
      // The WORKFLOWS are the resource (kind `workflow`): the shapes
      // of work this vault knows how to run. They live under `/workflows`
      // beside the other kinds' list pages, and a RUN of one lives under
      // `/runs` — a run is operational state, belongs to one machine and does
      // not sync, so it is not a vault asset and does not sit with the kinds.
      {
        path: "workflows",
        element: lazyPage(() => import("./pages/WorkflowTemplatesPage"), "WorkflowTemplatesPage"),
      },
      {
        path: "workflows/:uid",
        element: lazyPage(() => import("./pages/WorkflowTemplatePage"), "WorkflowTemplatePage"),
      },
      // Runs: the list is eager like every other landing list; the run's own
      // page pulls in the context table and the task's conversation page pulls
      // in the chat thread, so both load on first visit.
      {
        path: "runs",
        element: lazyPage(() => import("./pages/WorkflowRunsPage"), "WorkflowRunsPage"),
      },
      {
        path: "runs/:runId",
        element: lazyPage(() => import("./pages/WorkflowRunPage"), "WorkflowRunPage"),
      },
      // One task = one conversation, and that is where a run is driven.
      // The run's page links here; nothing else does.
      // One file the run reads or wrote. A page rather than a dialog: a file
      // a task produced is read, scrolled and linked to.
      {
        path: "runs/:runId/files",
        element: lazyPage(() => import("./pages/WorkflowFilePage"), "WorkflowFilePage"),
      },
      // The developer's own note, which is also the one thing in a run's
      // context they can rewrite.
      {
        path: "runs/:runId/notes/:noteRef",
        element: lazyPage(() => import("./pages/WorkflowNotePage"), "WorkflowNotePage"),
      },
      {
        path: "runs/:runId/nodes/:nodeKey",
        element: lazyPage(() => import("./pages/WorkflowNodePage"), "WorkflowNodePage"),
      },
      { path: "skills", element: <SkillsPage /> },
      {
        path: "skills/:uid",
        element: lazyPage(() => import("./pages/SkillDetailPage"), "SkillDetailPage"),
      },
      {
        path: "knowledge",
        element: lazyPage(() => import("./pages/KnowledgePage"), "KnowledgePage"),
      },
      {
        path: "knowledge/:uid",
        element: lazyPage(() => import("./pages/KnowledgeDetailPage"), "KnowledgeDetailPage"),
      },
      { path: "memory", element: lazyPage(() => import("./pages/MemoryPage"), "MemoryPage") },
      {
        path: "memory/:uid",
        element: lazyPage(() => import("./pages/MemoryDetailPage"), "MemoryDetailPage"),
      },
      { path: "sync", element: lazyPage(() => import("./pages/sync/SyncPage"), "SyncPage") },
      { path: "model-providers", element: <ModelProvidersPage /> },
      {
        path: "model-providers/:uid",
        element: lazyPage(() => import("./pages/ProviderDetailPage"), "ProviderDetailPage"),
      },
      // Legacy route — `knowledge_base` was a resource kind with its own
      // surface before it merged into the one Knowledge kind. Keep old
      // bookmarks for the LIST working by redirecting to the merged path.
      //
      // There is deliberately no redirect for an individual collection. A
      // detail URL is now built from the collection's uid, and an old link
      // carries its name — translating one into the other would mean a lookup
      // by name, which is exactly the addressing this change removed. Such a
      // link lands on the list, from which the collection is one click away.
      { path: "knowledge-bases", element: <Navigate to="/knowledge" replace /> },
      {
        path: "activity",
        element: lazyPage(() => import("./pages/activity/ActivityPage"), "ActivityPage"),
      },
      // Legacy routes — the audit log had its own page at /audit, and
      // "Observability" was the name this surface carried before Activity
      // gathered all three records. Keep old bookmarks and links working by
      // redirecting to the page that now holds what they were asking for.
      { path: "audit", element: <Navigate to="/activity" replace /> },
      { path: "observability", element: <Navigate to="/activity" replace /> },
      {
        path: "settings",
        element: lazyPage(() => import("./pages/settings/SettingsLayout"), "SettingsLayout"),
        children: [
          {
            index: true,
            element: <Navigate to="/settings/general" replace />,
          },
          {
            path: "general",
            element: lazyPage(() => import("./pages/settings/GeneralSettings"), "GeneralSettings"),
          },
          {
            path: "engine",
            element: lazyPage(() => import("./pages/settings/EngineSettings"), "EngineSettings"),
          },
          // Legacy routes — this surface used to live under Settings as
          // "LLM connections" (and before that as separate Models/Providers
          // pages). It is now /model-providers under RESOURCES. Keep old
          // bookmarks and links working by redirecting.
          { path: "llm-connections", element: <Navigate to="/model-providers" replace /> },
          { path: "models", element: <Navigate to="/model-providers" replace /> },
          { path: "providers", element: <Navigate to="/model-providers" replace /> },
          {
            path: "data",
            element: lazyPage(() => import("./pages/settings/DataSettings"), "DataSettings"),
          },
          // Legacy route — there is no embedding configuration any more:
          // knowledge is a directory of files an agent greps, so no index
          // needs an embedding model (ADR knowledge-is-plain-files). An old
          // bookmark lands on "Coffer's model" — the nearest live surface,
          // where the model Coffer's own passes run on is configured — rather
          // than on the 404 page.
          { path: "embedding", element: <Navigate to="/settings/engine" replace /> },
          // Legacy route — Sync was a Settings tab before it became a
          // top-level page. Keep old bookmarks and links working.
          { path: "sync", element: <Navigate to="/sync" replace /> },
          {
            path: "security",
            element: lazyPage(
              () => import("./pages/settings/SecuritySettings"),
              "SecuritySettings",
            ),
          },
          {
            path: "about",
            element: lazyPage(() => import("./pages/settings/AboutPage"), "AboutPage"),
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
