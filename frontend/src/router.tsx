import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AgentsPage } from "./pages/AgentsPage";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { SkillsPage } from "./pages/SkillsPage";
import { SkillDetailPage } from "./pages/SkillDetailPage";
import { ChatPage } from "./pages/ChatPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { ResourceDetailPage } from "./pages/ResourceDetailPage";
import { AuditLogPage } from "./pages/audit/AuditLogPage";
import { SettingsLayout } from "./pages/settings/SettingsLayout";
import { GeneralSettings } from "./pages/settings/GeneralSettings";
import { DataSettings } from "./pages/settings/DataSettings";
import { AppSettings } from "./pages/settings/AppSettings";
import { AboutPage } from "./pages/settings/AboutPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/agents" replace /> },
      { path: "mcp-servers", element: <ResourcesPage /> },
      { path: "mcp-servers/:kind/:name", element: <ResourceDetailPage /> },
      // Legacy route — this surface used to live at /resources. Keep old
      // bookmarks and links working by redirecting to the renamed path.
      { path: "resources", element: <Navigate to="/mcp-servers" replace /> },
      { path: "agents", element: <AgentsPage /> },
      { path: "agents/:name", element: <AgentDetailPage /> },
      { path: "chat", element: <ChatPage /> },
      { path: "chat/:id", element: <ChatPage /> },
      { path: "skills", element: <SkillsPage /> },
      { path: "skills/:name", element: <SkillDetailPage /> },
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
          { path: "data", element: <DataSettings /> },
          { path: "app", element: <AppSettings /> },
          { path: "about", element: <AboutPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
