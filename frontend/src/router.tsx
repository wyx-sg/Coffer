import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AgentsPage } from "./pages/AgentsPage";
import { SkillsPage } from "./pages/SkillsPage";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { KnowledgeBaseAddPage } from "./pages/KnowledgeBaseAddPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { ResourceDetailPage } from "./pages/ResourceDetailPage";
import { ObservabilityPage } from "./pages/observability/ObservabilityPage";
import { SettingsLayout } from "./pages/settings/SettingsLayout";
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
      { path: "skills", element: <SkillsPage /> },
      { path: "knowledge-bases", element: <KnowledgeBasesPage /> },
      { path: "knowledge-bases/new", element: <KnowledgeBaseAddPage /> },
      { path: "observability", element: <ObservabilityPage /> },
      // Legacy route — the audit log lived at /audit before it became the
      // Observability page. Keep the URL working so bookmarks resolve.
      {
        path: "audit",
        element: <Navigate to="/observability" replace />,
      },
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="/settings/data" replace />,
          },
          { path: "data", element: <DataSettings /> },
          { path: "app", element: <AppSettings /> },
          { path: "about", element: <AboutPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
