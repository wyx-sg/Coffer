import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { Layout } from "./components/Layout";
import { LegacyScopeRedirect } from "./components/LegacyScopeRedirect";
import { LegacyMcpServerRedirect } from "./components/mcp/LegacyMcpServerRedirect";
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
        path: "mcp-servers/:name",
        element: lazyPage(() => import("./pages/ResourceDetailPage"), "ResourceDetailPage"),
      },
      // Legacy routes — this surface used to live at /resources, and the
      // detail page carried a kind segment that only ever said `mcp_server`.
      // Keep old bookmarks and links working by redirecting to the renamed
      // paths.
      { path: "mcp-servers/mcp_server/:name", element: <LegacyMcpServerRedirect /> },
      { path: "resources", element: <Navigate to="/mcp-servers" replace /> },
      { path: "agents", element: <AgentsPage /> },
      {
        path: "agents/:name",
        element: lazyPage(() => import("./pages/AgentDetailPage"), "AgentDetailPage"),
      },
      // Detail pages reached by clicking a row on the agent's Memory /
      // Conversations tabs. Each identifies its subject by a search param (the
      // store's `dir`, the session's `path`) rather than a path segment,
      // because both identities are absolute filesystem paths — a path segment
      // would have to survive encoding its own separators.
      {
        path: "agents/:name/conversations",
        element: lazyPage(() => import("./pages/AgentConversationPage"), "AgentConversationPage"),
      },
      {
        path: "agents/:name/memory",
        element: lazyPage(() => import("./pages/AgentMemoryStorePage"), "AgentMemoryStorePage"),
      },
      { path: "channels", element: <ChannelsPage /> },
      {
        path: "channels/:name",
        element: lazyPage(() => import("./pages/ChannelDetailPage"), "ChannelDetailPage"),
      },
      { path: "skills", element: <SkillsPage /> },
      {
        path: "skills/:name",
        element: lazyPage(() => import("./pages/SkillDetailPage"), "SkillDetailPage"),
      },
      {
        path: "knowledge",
        element: lazyPage(() => import("./pages/KnowledgePage"), "KnowledgePage"),
      },
      {
        path: "knowledge/:name",
        element: lazyPage(() => import("./pages/KnowledgeDetailPage"), "KnowledgeDetailPage"),
      },
      { path: "memory", element: lazyPage(() => import("./pages/MemoryPage"), "MemoryPage") },
      {
        path: "memory/:name",
        element: lazyPage(() => import("./pages/MemoryDetailPage"), "MemoryDetailPage"),
      },
      { path: "sync", element: lazyPage(() => import("./pages/sync/SyncPage"), "SyncPage") },
      { path: "model-providers", element: <ModelProvidersPage /> },
      {
        path: "model-providers/:name",
        element: lazyPage(() => import("./pages/ProviderDetailPage"), "ProviderDetailPage"),
      },
      // Legacy route — `knowledge_base` was a resource kind with its own
      // surface before it merged into the one Knowledge kind. Keep old
      // bookmarks and links working by redirecting to the merged path.
      // (`memory` used to redirect here too, before spec memory split it back
      // out into its own kind and surface above.)
      { path: "knowledge-bases", element: <Navigate to="/knowledge" replace /> },
      { path: "knowledge-bases/:name", element: <LegacyScopeRedirect /> },
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
