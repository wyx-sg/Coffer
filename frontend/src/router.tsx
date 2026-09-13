import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { Layout } from "./components/Layout";
import { LegacyScopeRedirect } from "./components/LegacyScopeRedirect";
import { AgentsPage } from "./pages/AgentsPage";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { ChatPage } from "./pages/ChatPage";
import { ChannelsPage } from "./pages/ChannelsPage";
import { ChannelDetailPage } from "./pages/ChannelDetailPage";
import { SkillsPage } from "./pages/SkillsPage";
import { SkillDetailPage } from "./pages/SkillDetailPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { KnowledgeDetailPage } from "./kinds/knowledge/KnowledgeDetailPage";
import { ActivityPage } from "./pages/activity/ActivityPage";
import { MemoryPage } from "./pages/MemoryPage";
import { MemoryDetailPage } from "./kinds/memory/MemoryDetailPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { ResourceDetailPage } from "./pages/ResourceDetailPage";
import { SettingsLayout } from "./pages/settings/SettingsLayout";
import { GeneralSettings } from "./pages/settings/GeneralSettings";
import { DataSettings } from "./pages/settings/DataSettings";
import { EngineSettings } from "./pages/settings/EngineSettings";
import { SecuritySettings } from "./pages/settings/SecuritySettings";
import { SyncSettings } from "./pages/settings/SyncSettings";
import { AboutPage } from "./pages/settings/AboutPage";
import { ModelProvidersPage } from "./pages/ModelProvidersPage";
import { ProviderDetailPage } from "./pages/ProviderDetailPage";
import { NotFoundPage } from "./pages/NotFoundPage";

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
      { path: "chat", element: <ChatPage /> },
      { path: "chat/:id", element: <ChatPage /> },
      { path: "mcp-servers", element: <ResourcesPage /> },
      { path: "mcp-servers/:kind/:name", element: <ResourceDetailPage /> },
      // Legacy route — this surface used to live at /resources. Keep old
      // bookmarks and links working by redirecting to the renamed path.
      { path: "resources", element: <Navigate to="/mcp-servers" replace /> },
      { path: "agents", element: <AgentsPage /> },
      { path: "agents/:name", element: <AgentDetailPage /> },
      { path: "channels", element: <ChannelsPage /> },
      { path: "channels/:name", element: <ChannelDetailPage /> },
      { path: "skills", element: <SkillsPage /> },
      { path: "skills/:name", element: <SkillDetailPage /> },
      { path: "knowledge", element: <KnowledgePage /> },
      { path: "knowledge/:scope", element: <KnowledgeDetailPage /> },
      { path: "memory", element: <MemoryPage /> },
      { path: "memory/:name", element: <MemoryDetailPage /> },
      { path: "model-providers", element: <ModelProvidersPage /> },
      { path: "model-providers/:name", element: <ProviderDetailPage /> },
      // Legacy route — `knowledge_base` was a resource kind with its own
      // surface before it merged into the one Knowledge kind. Keep old
      // bookmarks and links working by redirecting to the merged path.
      // (`memory` used to redirect here too, before spec memory split it back
      // out into its own kind and surface above.)
      { path: "knowledge-bases", element: <Navigate to="/knowledge" replace /> },
      { path: "knowledge-bases/:name", element: <LegacyScopeRedirect /> },
      { path: "activity", element: <ActivityPage /> },
      // Legacy routes — the audit log had its own page at /audit, and
      // "Observability" was the name this surface carried before Activity
      // gathered all three records. Keep old bookmarks and links working by
      // redirecting to the page that now holds what they were asking for.
      { path: "audit", element: <Navigate to="/activity" replace /> },
      { path: "observability", element: <Navigate to="/activity" replace /> },
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="/settings/general" replace />,
          },
          { path: "general", element: <GeneralSettings /> },
          { path: "engine", element: <EngineSettings /> },
          // Legacy routes — this surface used to live under Settings as
          // "LLM connections" (and before that as separate Models/Providers
          // pages). It is now /model-providers under RESOURCES. Keep old
          // bookmarks and links working by redirecting.
          { path: "llm-connections", element: <Navigate to="/model-providers" replace /> },
          { path: "models", element: <Navigate to="/model-providers" replace /> },
          { path: "providers", element: <Navigate to="/model-providers" replace /> },
          { path: "data", element: <DataSettings /> },
          // Legacy route — embedding/chunking config is now one of the two
          // cards on the Engine tab. Keep old bookmarks working by redirecting.
          { path: "embedding", element: <Navigate to="/settings/engine" replace /> },
          { path: "sync", element: <SyncSettings /> },
          { path: "security", element: <SecuritySettings /> },
          { path: "about", element: <AboutPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
