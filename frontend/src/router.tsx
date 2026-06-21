import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AgentsPage } from "./pages/AgentsPage";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { ChatPage } from "./pages/ChatPage";
import { ChannelsPage } from "./pages/ChannelsPage";
import { ChannelDetailPage } from "./pages/ChannelDetailPage";
import { SkillsPage } from "./pages/SkillsPage";
import { SkillDetailPage } from "./pages/SkillDetailPage";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { KnowledgeBaseDetailPage } from "./kinds/knowledge_base/KnowledgeBaseDetailPage";
import { MemoryPage } from "./pages/MemoryPage";
import { MemoryStoreDetailPage } from "./kinds/memory/MemoryStoreDetailPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { ResourceDetailPage } from "./pages/ResourceDetailPage";
import { AuditLogPage } from "./pages/audit/AuditLogPage";
import { SettingsLayout } from "./pages/settings/SettingsLayout";
import { GeneralSettings } from "./pages/settings/GeneralSettings";
import { DataSettings } from "./pages/settings/DataSettings";
import { SecuritySettings } from "./pages/settings/SecuritySettings";
import { SyncSettings } from "./pages/settings/SyncSettings";
import { AboutPage } from "./pages/settings/AboutPage";
import { LlmConnectionsPage } from "./pages/settings/LlmConnectionsPage";
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
      { path: "knowledge-bases", element: <KnowledgeBasesPage /> },
      { path: "knowledge-bases/:name", element: <KnowledgeBaseDetailPage /> },
      { path: "memory", element: <MemoryPage /> },
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
          { path: "llm-connections", element: <LlmConnectionsPage /> },
          // Legacy routes — the separate Models page is retired and Providers is
          // folded into the unified LLM Connections page. Keep old bookmarks and
          // links working by redirecting.
          { path: "models", element: <Navigate to="/settings/llm-connections" replace /> },
          { path: "providers", element: <Navigate to="/settings/llm-connections" replace /> },
          { path: "data", element: <DataSettings /> },
          // Legacy route — embedding/chunking config merged into the LLM
          // Connections page. Keep old bookmarks and links working by redirecting.
          { path: "embedding", element: <Navigate to="/settings/llm-connections" replace /> },
          { path: "sync", element: <SyncSettings /> },
          { path: "security", element: <SecuritySettings /> },
          { path: "about", element: <AboutPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
