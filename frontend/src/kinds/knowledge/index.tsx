// frontend/src/kinds/knowledge/index.tsx
import { Library } from "lucide-react";
import type { KindUIModule } from "@/lib/components/kindRegistry";
import { KnowledgeScopeCard } from "./KnowledgeScopeCard";
import { KnowledgeDetailPage } from "./KnowledgeDetailPage";

export const KNOWLEDGE_KIND_UI: KindUIModule = {
  name: "knowledge",
  displayName: "Knowledge",
  icon: Library,
  Card: KnowledgeScopeCard,
  // No ``addPath``: the KnowledgePage owns "add" itself via an in-page dialog
  // (KnowledgeAddDialog), and the global / per-project scopes auto-provision.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <KnowledgeDetailPage />,
};
