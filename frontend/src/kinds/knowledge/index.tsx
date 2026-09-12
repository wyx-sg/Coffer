// frontend/src/kinds/knowledge/index.tsx
import { Library } from "lucide-react";
import type { KindUIModule } from "@/lib/components/kindRegistry";
import { KnowledgeDetailPage } from "./KnowledgeDetailPage";

export const KNOWLEDGE_KIND_UI: KindUIModule = {
  name: "knowledge",
  displayName: "Knowledge",
  icon: Library,
  // A collection is a folder, so its row says what a folder says.
  Card: ({ resource }) => <span className="font-medium">{resource.name}</span>,
  // No ``addPath``: the KnowledgePage owns creation itself, through an in-page
  // dialog, because a collection is a directory as much as a row.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <KnowledgeDetailPage />,
};
