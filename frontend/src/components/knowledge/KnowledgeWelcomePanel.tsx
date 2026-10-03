// frontend/src/components/knowledge/KnowledgeWelcomePanel.tsx
// First run on /knowledge (board 5.1.09): no collection yet. Nothing
// auto-provisions one (spec knowledge "Create collections only deliberately"),
// so the page is the standard empty state — what a collection is, and the one
// deliberate first step, New collection.
import { Book, FolderPlus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

interface Props {
  onCreate: () => void;
}

export function KnowledgeWelcomePanel({ onCreate }: Props) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={Book}
      title={t("knowledge.welcome.title")}
      description={t("knowledge.welcome.body")}
      action={
        <Button onClick={onCreate}>
          <FolderPlus aria-hidden /> {t("knowledge.create.title")}
        </Button>
      }
      className="min-h-full"
    />
  );
}
