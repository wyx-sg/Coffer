import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AgentsPage } from "./pages/AgentsPage";
import { AgentDetailPage } from "./pages/AgentDetailPage";
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
      { index: true, element: <Navigate to="/resources" replace /> },
      { path: "resources", element: <ResourcesPage /> },
      { path: "resources/:kind/:name", element: <ResourceDetailPage /> },
      { path: "agents", element: <AgentsPage /> },
      { path: "agents/:name", element: <AgentDetailPage /> },
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
