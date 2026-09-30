import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ChatRedirect, SettingsIndexRedirect } from "./components/shell/redirects";
import { FeatureGate } from "./components/FeatureGate";
import { PageFallback } from "./components/PageFallback";
import type { FeatureKey } from "./lib/hooks/useFeatures";
import { AgentsPage } from "./pages/AgentsPage";
import { ChannelsPage } from "./pages/ChannelsPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { ModelProvidersPage } from "./pages/ModelProvidersPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";

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

/** A page that belongs to an experimental feature: while the feature is off
 *  the route renders a notice saying so instead. */
function gated(feature: FeatureKey, page: JSX.Element): JSX.Element {
  return <FeatureGate feature={feature}>{page}</FeatureGate>;
}

const knowledgePage = gated(
  "knowledge",
  lazyPage(() => import("./pages/KnowledgePage"), "KnowledgePage"),
);
const memoryDetailPage = gated(
  "memory",
  lazyPage(() => import("./pages/MemoryDetailPage"), "MemoryDetailPage"),
);

const conversationsPage = lazyPage(() => import("./pages/ConversationsPage"), "ConversationsPage");

const settingsModal = lazyPage(() => import("./pages/settings/SettingsModal"), "SettingsModal");

// The route table, exported as data: a test that has to prove a URL lands
// somewhere (rather than on "page not found") needs the real table, and
// rebuilding it in the test would prove nothing about this one.
//
// Two tables, because Settings is a modal and not a page (spec web-ui "Open
// Settings as a modal from the sidebar footer"): the shell renders `pageRoutes`
// against the location of the page the user is on — the one under the modal
// while Settings is open — and `settingsRoutes` over it. `routes` mounts the
// shell at `*` so both are its descendants.
//
// Detail routes follow one rule (spec web-ui "Lay out every detail page's tabs
// alike"): `/<kind>/<id>/<tab>`, the default tab at the bare path. `<id>` is the
// name where a kind's name is fixed — skills and MCP servers — and the immutable
// uid where a name can be renamed (ADR resource-identity-is-an-immutable-uid);
// each page redirects an old `?tab=` or old uid address to the new one.
const pageRoutes: RouteObject[] = [
  { index: true, element: <OverviewPage /> },
  // One element for both addresses, so opening a conversation from the list —
  // or the draft's first send landing on the conversation it created — keeps
  // the page mounted and its state (the draft's pending first message) alive.
  { path: "conversations", element: conversationsPage },
  { path: "conversations/:id", element: conversationsPage },
  // Legacy routes — Conversations was Chat.
  { path: "chat", element: <ChatRedirect /> },
  { path: "chat/:id", element: <ChatRedirect /> },
  { path: "mcp-servers", element: <ResourcesPage /> },
  { path: "mcp-servers/:name", element: <ResourcesPage /> },
  { path: "mcp-servers/:name/:tab", element: <ResourcesPage /> },
  // Legacy route — this surface used to live at /resources.
  { path: "resources", element: <Navigate to="/mcp-servers" replace /> },
  {
    path: "custom-tools",
    element: lazyPage(() => import("./pages/CustomToolsPage"), "CustomToolsPage"),
  },
  // One custom-tool group, by its fixed name — one page with no tabs.
  {
    path: "custom-tools/:group",
    element: lazyPage(() => import("./pages/CustomToolsPage"), "CustomToolsPage"),
  },
  { path: "clis", element: lazyPage(() => import("./pages/ClisPage"), "ClisPage") },
  // One required command, by the command itself, open beside the list.
  { path: "clis/:command", element: lazyPage(() => import("./pages/ClisPage"), "ClisPage") },
  { path: "agents", element: <AgentsPage /> },
  // An agent's pages are addressed by its TYPE (one agent per type), the
  // detail page's tab by the path (`/agents/<type>/<tab>`, Overview bare),
  // and every page opened from a tab is nested under it. An old uid address,
  // `?tab=` and the old Conversations tab are redirected by `useAgentRoute`.
  {
    path: "agents/:type",
    element: lazyPage(() => import("./pages/AgentDetailPage"), "AgentDetailPage"),
  },
  {
    path: "agents/:type/:tab",
    element: lazyPage(() => import("./pages/AgentDetailPage"), "AgentDetailPage"),
  },
  // One native memory store, from the Memory tab. Its identity is its
  // directory, an absolute path, so it rides in `?dir=` rather than a segment.
  {
    path: "agents/:type/memory/store",
    element: lazyPage(() => import("./pages/AgentMemoryStorePage"), "AgentMemoryStorePage"),
  },
  // An unmanaged skill folder, from the Skills tab. It has no uid of its own,
  // so the scan's location and the folder name name it.
  {
    path: "agents/:type/skills/unmanaged/:location/:name",
    element: lazyPage(() => import("./pages/UnmanagedSkillDetailPage"), "UnmanagedSkillDetailPage"),
  },
  // A direct (unmanaged) MCP server of the agent, from the MCP servers tab:
  // the entry's name, and `?source=` for the file when two share that name.
  {
    path: "agents/:type/mcp-servers/:entry",
    element: lazyPage(() => import("./pages/AgentMcpEntryPage"), "AgentMcpEntryPage"),
  },
  // A plugin, from the Plugins tab (`<name>@<marketplace>`, one segment).
  {
    path: "agents/:type/plugins/:pluginId",
    element: lazyPage(() => import("./pages/AgentPluginPage"), "AgentPluginPage"),
  },
  // The Channels page is the list beside the open channel, so all three
  // addresses render the same page (the tab is the optional last segment).
  { path: "channels", element: <ChannelsPage /> },
  { path: "channels/:uid", element: <ChannelsPage /> },
  { path: "channels/:uid/:tab", element: <ChannelsPage /> },
  // The Skills page is the library beside the open skill, so all three
  // addresses render the same page; it loads the detail pane on first open.
  { path: "skills", element: <SkillsPage /> },
  { path: "skills/:name", element: <SkillsPage /> },
  { path: "skills/:name/:tab", element: <SkillsPage /> },
  // Knowledge is ONE page (spec knowledge "Present a collection as one tree in
  // the web UI"): the collection tree stays on the left whatever the right pane
  // shows — Recent changes (`/knowledge`), one change (`/knowledge/changes/<version>`),
  // a collection and its open document (`/knowledge/<uid>?file=`), the
  // document's History (`/knowledge/<uid>/history?file=`) or the Inbox
  // (`/knowledge/<uid>/inbox`). Every address reuses the same element, so moving
  // between them keeps the tree's expanded folders rather than remounting it.
  { path: "knowledge", element: knowledgePage },
  { path: "knowledge/changes/:version", element: knowledgePage },
  { path: "knowledge/:uid", element: knowledgePage },
  { path: "knowledge/:uid/:tab", element: knowledgePage },
  {
    path: "memory",
    element: gated(
      "memory",
      lazyPage(() => import("./pages/MemoryPage"), "MemoryPage"),
    ),
  },
  // A partition's two tabs: Memories (the bare path) and Delivered.
  { path: "memory/:uid", element: memoryDetailPage },
  { path: "memory/:uid/:tab", element: memoryDetailPage },
  {
    path: "sync",
    element: gated(
      "vault_sync",
      lazyPage(() => import("./pages/sync/SyncPage"), "SyncPage"),
    ),
  },
  { path: "model-providers", element: <ModelProvidersPage /> },
  {
    path: "model-providers/:uid",
    element: lazyPage(() => import("./pages/ProviderDetailPage"), "ProviderDetailPage"),
  },
  {
    path: "model-providers/:uid/:tab",
    element: lazyPage(() => import("./pages/ProviderDetailPage"), "ProviderDetailPage"),
  },
  // Legacy route — `knowledge_base` was a resource kind with its own
  // surface before it merged into the one Knowledge kind. Keep old
  // bookmarks for the LIST working by redirecting to the merged path.
  //
  // There is deliberately no redirect for an individual collection. A
  // detail URL is built from the collection's uid, and an old link carries
  // its name — such a link lands on the list, from which the collection is
  // one click away.
  { path: "knowledge-bases", element: <Navigate to="/knowledge" replace /> },
  { path: "secrets", element: lazyPage(() => import("./pages/SecretsPage"), "SecretsPage") },
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
  { path: "usage", element: lazyPage(() => import("./pages/UsagePage"), "UsagePage") },
  { path: "*", element: <NotFoundPage /> },
];

/** The Settings modal's routes, rendered over the page underneath. */
const settingsRoutes: RouteObject[] = [
  { path: "settings", element: <SettingsIndexRedirect /> },
  // Legacy routes — Coffer's model was a tab of its own before it became a
  // section of General (spec web-ui "Choose Coffer's model in Settings ›
  // General"), and `/settings/embedding` is an old bookmark only: there is no
  // embedding configuration (ADR knowledge-is-plain-files).
  { path: "settings/engine", element: <Navigate to="/settings/general" replace /> },
  { path: "settings/embedding", element: <Navigate to="/settings/general" replace /> },
  // Legacy routes — this surface used to live under Settings as "LLM
  // connections" (and before that as separate Models/Providers pages). It is
  // /model-providers now. Keep old bookmarks and links working.
  { path: "settings/llm-connections", element: <Navigate to="/model-providers" replace /> },
  { path: "settings/models", element: <Navigate to="/model-providers" replace /> },
  { path: "settings/providers", element: <Navigate to="/model-providers" replace /> },
  // Legacy route — Sync was a Settings tab before it became a page.
  { path: "settings/sync", element: <Navigate to="/sync" replace /> },
  { path: "settings/:tab", element: settingsModal },
];

/** Every route the app answers, pages and Settings alike — what a test that
 *  resolves a path against the real table reads. */
export const appRoutes: RouteObject[] = [...pageRoutes, ...settingsRoutes];

export const routes: RouteObject[] = [
  { path: "*", element: <Layout pageRoutes={pageRoutes} settingsRoutes={settingsRoutes} /> },
];

export const router = createBrowserRouter(routes);
