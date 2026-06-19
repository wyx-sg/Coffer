import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AgentsPage } from "./pages/AgentsPage";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { ChatPage } from "./pages/ChatPage";
import { ChannelsPage } from "./pages/ChannelsPage";
import { ChannelDetailPage } from "./pages/ChannelDetailPage";
import { SkillsPage } from "./pages/SkillsPage";
import { SkillDetailPage } from "./pages/SkillDetailPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { KnowledgeBaseDetailPage } from "./kinds/knowledge_base/KnowledgeBaseDetailPage";
import { MemoryStoreDetailPage } from "./kinds/memory/MemoryStoreDetailPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { ResourceDetailPage } from "./pages/ResourceDetailPage";
import { AuditLogPage } from "./pages/audit/AuditLogPage";
import { SettingsLayout } from "./pages/settings/SettingsLayout";
import { GeneralSettings } from "./pages/settings/GeneralSettings";
import { DataSettings } from "./pages/settings/DataSettings";
import { AppSettings } from "./pages/settings/AppSettings";
import { SecuritySettings } from "./pages/settings/SecuritySettings";
import { SyncSettings } from "./pages/settings/SyncSettings";
import { AboutPage } from "./pages/settings/AboutPage";
import { ModelsPage } from "./pages/settings/ModelsPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export const router = createBrowserRouter([
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
      // The unified 知识 surface (ADR-030) replaces the split Memory +
      // Knowledge-base pages. Scope is a route param so it deep-links.
      { path: "knowledge", element: <KnowledgePage /> },
      { path: "knowledge/:scopeId", element: <KnowledgePage /> },
      // Legacy routes — these surfaces used to live at /memory and
      // /knowledge-bases. Redirect old bookmarks to the unified page (mirrors
      // the /resources and /observability redirects). The per-store / per-KB
      // detail pages stay reachable for the in-page links into them.
      { path: "memory", element: <Navigate to="/knowledge" replace /> },
      { path: "knowledge-bases", element: <Navigate to="/knowledge" replace /> },
      { path: "knowledge-bases/:name", element: <KnowledgeBaseDetailPage /> },
      { path: "memory/:name", element: <MemoryStoreDetailPage /> },
      { path: "audit", element: <AuditLogPage /> },
      // Legacy route — this surface briefly lived at /observability. Keep the
      // URL working so old bookmarks resolve.
      {
        path: "observability",
        element: <Navigate to="/audit" replace />,
      },
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="/settings/general" replace />,
          },
          { path: "general", element: <GeneralSettings /> },
          { path: "models", element: <ModelsPage /> },
          { path: "data", element: <DataSettings /> },
          // Legacy route — embedding/chunking config merged into the Models
          // page. Keep old bookmarks and links working by redirecting.
          { path: "embedding", element: <Navigate to="/settings/models" replace /> },
          { path: "sync", element: <SyncSettings /> },
          { path: "security", element: <SecuritySettings /> },
          { path: "app", element: <AppSettings /> },
          { path: "about", element: <AboutPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
