// frontend/src/kinds/knowledge_base/index.tsx
import { BookOpen } from "lucide-react";
import type { KindUIModule } from "@/lib/components/kindRegistry";
import { KnowledgeBaseCard } from "./KnowledgeBaseCard";
import { KnowledgeBaseDetailPage } from "./KnowledgeBaseDetailPage";

export const KNOWLEDGE_BASE_KIND_UI: KindUIModule = {
  name: "knowledge_base",
  displayName: "Knowledge Base",
  icon: BookOpen,
  Card: KnowledgeBaseCard,
  // Router registers the add page at /knowledge-bases/new (see router.tsx).
  // The old /resources/knowledge_base/new value rendered a 404 — mirror the
  // memory kind's CODE26-036 fix.
  addPath: "/knowledge-bases/new",
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <KnowledgeBaseDetailPage />,
};
