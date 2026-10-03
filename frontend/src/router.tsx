import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { Layout } from "./components/Layout";
import { UnsavedGuardProvider } from "./components/shell/UnsavedGuard";
import { SettingsIndexRedirect } from "./components/shell/redirects";
import { FeatureGate } from "./components/FeatureGate";
import { PageFallback } from "./components/PageFallback";
import type { FeatureKey } from "./lib/hooks/useFeatures";
import { NAV_GROUPS, type NavEntry } from "./lib/navigation";
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
 *  the route renders the standard not-found page, as if the page did not exist
 *  (spec experimental-features "Close every surface of a switched-off
 *  feature"). A page is gated here by
 *  the `feature` its sidebar entry carries in `lib/navigation.ts`, so one flag
 *  on the entry closes both. */
const FEATURE_OF_PATH = new Map<string, FeatureKey>(
  NAV_GROUPS.flatMap((g) => g.entries)
    .filter((e): e is NavEntry & { feature: FeatureKey } => e.feature !== undefined)
    .map((e) => [e.to.replace(/^\//, ""), e.feature]),
);

/** Wrap every route under a flagged entry's path in its `FeatureGate`. */
function gateRoutes(table: RouteObject[]): RouteObject[] {
  return table.map((route) => {
    const top = route.path?.split("/")[0];
    const feature = top === undefined ? undefined : FEATURE_OF_PATH.get(top);
    if (feature === undefined || route.element === undefined) return route;
    return {
      ...route,
      element: (
        <FeatureGate feature={feature} notFound={<NotFoundPage />}>
          {route.element}
        </FeatureGate>
      ),
    };
  });
}

const knowledgePage = lazyPage(() => import("./pages/KnowledgePage"), "KnowledgePage");
const memoryDetailPage = lazyPage(() => import("./pages/MemoryDetailPage"), "MemoryDetailPage");

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
// uid where a name can be renamed (ADR identity-is-the-uid-inside-the-file).
const pageRoutes: RouteObject[] = gateRoutes([
  { index: true, element: <OverviewPage /> },
  // One element for both addresses, so opening a conversation from the list —
  // or the draft's first send landing on the conversation it created — keeps
  // the page mounted and its state (the draft's pending first message) alive.
  { path: "conversations", element: conversationsPage },
  { path: "conversations/:id", element: conversationsPage },
  { path: "mcp-servers", element: <ResourcesPage /> },
  { path: "mcp-servers/:name", element: <ResourcesPage /> },
  { path: "mcp-servers/:name/:tab", element: <ResourcesPage /> },
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
  // One command-line tool, by the command itself, open beside the list; its
  // tab (Overview bare, Commands) is the path.
  { path: "clis/:command", element: lazyPage(() => import("./pages/ClisPage"), "ClisPage") },
  { path: "clis/:command/:tab", element: lazyPage(() => import("./pages/ClisPage"), "ClisPage") },
  { path: "agents", element: <AgentsPage /> },
  // An agent's pages are addressed by its TYPE (one agent per type), the
  // detail page's tab by the path (`/agents/<type>/<tab>`, Overview bare),
  // and every page opened from a tab is nested under it.
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
    element: lazyPage(() => import("./pages/MemoryPage"), "MemoryPage"),
  },
  // A partition's two tabs: Memories (the bare path) and Delivered.
  { path: "memory/:uid", element: memoryDetailPage },
  { path: "memory/:uid/:tab", element: memoryDetailPage },
  {
    path: "sync",
    element: lazyPage(() => import("./pages/sync/SyncPage"), "SyncPage"),
  },
  // Sub-views of a stopped round, without tabs, each with a "‹ Sync" back link.
  {
    path: "sync/conflicts",
    element: lazyPage(
      () => import("./pages/sync/SyncResolveConflictsPage"),
      "SyncResolveConflictsPage",
    ),
  },
  {
    path: "sync/deletions",
    element: lazyPage(
      () => import("./pages/sync/SyncDeletionReviewPage"),
      "SyncDeletionReviewPage",
    ),
  },
  // One page: the Providers list beside the open provider, and the Usage tab.
  // `usage` is declared before `:uid` so it is never read as a provider.
  { path: "model-providers", element: <ModelProvidersPage /> },
  { path: "model-providers/usage", element: <ModelProvidersPage /> },
  { path: "model-providers/:uid", element: <ModelProvidersPage /> },
  { path: "secrets", element: lazyPage(() => import("./pages/SecretsPage"), "SecretsPage") },
  {
    path: "activity",
    element: lazyPage(() => import("./pages/activity/ActivityPage"), "ActivityPage"),
  },
  { path: "*", element: <NotFoundPage /> },
]);

/** The Settings modal's routes, rendered over the page underneath. */
const settingsRoutes: RouteObject[] = [
  { path: "settings", element: <SettingsIndexRedirect /> },
  { path: "settings/:tab", element: settingsModal },
];

/** Every route the app answers, pages and Settings alike — what a test that
 *  resolves a path against the real table reads. */
export const appRoutes: RouteObject[] = [...pageRoutes, ...settingsRoutes];

export const routes: RouteObject[] = [
  {
    path: "*",
    element: (
      <UnsavedGuardProvider>
        <Layout pageRoutes={pageRoutes} settingsRoutes={settingsRoutes} />
      </UnsavedGuardProvider>
    ),
  },
];

export const router = createBrowserRouter(routes);
