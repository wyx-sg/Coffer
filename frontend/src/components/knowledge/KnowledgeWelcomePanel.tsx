// frontend/src/components/knowledge/KnowledgeWelcomePanel.tsx
// First run on /knowledge (board 5.1.09): no collection yet. Nothing
// auto-provisions one (spec knowledge "Create collections only deliberately"),
// so the page is the standard empty state — what a collection is, and the two
// deliberate first steps: New collection, which Coffer keeps, or Link an
// external folder, which stays where it is and is only shared with the agents.
import { Book, FolderPlus, FolderSymlink } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

interface Props {
  onCreate: () => void;
  onLink: () => void;
}

export function KnowledgeWelcomePanel({ onCreate, onLink }: Props) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={Book}
      title={t("knowledge.welcome.title")}
      description={t("knowledge.welcome.body")}
      action={
        <div className="flex flex-wrap justify-center gap-2">
          <Button onClick={onCreate}>
            <FolderPlus aria-hidden /> {t("knowledge.create.title")}
          </Button>
          <Button variant="outline" onClick={onLink}>
            <FolderSymlink aria-hidden /> {t("knowledge.add.link")}
          </Button>
        </div>
      }
      className="min-h-full"
    />
  );
}
