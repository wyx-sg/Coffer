// frontend/src/components/knowledge/KnowledgeNoModelLine.tsx
//
// What the page says INSTEAD of an Inbox, the Automatic control and Curate
// now while Coffer's model is not set (spec knowledge "Present a collection as
// one tree in the web UI"; board 5.1.25): one muted line under the page title
// — set the model to curate new items into your documents — linking to
// Settings › General, where the model is chosen. Until then items become
// documents as they arrive.
import { useTranslation } from "react-i18next";

import { useOpenSettings } from "@/lib/settingsModal";

export function KnowledgeNoModelLine() {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-sm text-text-subtle">
      <span>{t("knowledge.noModel.line")}</span>
      <button
        type="button"
        className="font-label text-text hover:underline"
        onClick={() => openSettings("general")}
      >
        {t("knowledge.noModel.link")}
      </button>
    </span>
  );
}
