// frontend/src/components/knowledge/KnowledgeNoModelLine.tsx
//
// What the page says INSTEAD of an Inbox and Curate now while Coffer's model
// is not set (spec knowledge "Present a collection as one tree in the web
// UI"): one muted line — items become documents as they arrive — linking to
// Settings › General, where the model is chosen.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useOpenSettings } from "@/lib/settingsModal";

export function KnowledgeNoModelLine() {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  return (
    <p className="flex flex-wrap items-center gap-1 text-xs text-text-subtle">
      <span>{t("knowledge.noModel.line")}</span>
      <Button
        variant="link"
        size="sm"
        className="h-auto px-0"
        onClick={() => openSettings("general")}
      >
        {t("knowledge.noModel.link")}
      </Button>
    </p>
  );
}
