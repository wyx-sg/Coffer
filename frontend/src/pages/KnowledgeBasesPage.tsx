// frontend/src/pages/KnowledgeBasesPage.tsx
import { Library } from "lucide-react";
import { KindResourcePage } from "./KindResourcePage";

/** Knowledge-bases landing page (spec 005-knowledge-base). */
export function KnowledgeBasesPage() {
  return <KindResourcePage kind="knowledge_base" icon={Library} i18nKey="knowledgeBases" />;
}
