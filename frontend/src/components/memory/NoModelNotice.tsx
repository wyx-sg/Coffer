// frontend/src/components/memory/NoModelNotice.tsx — why memories are not merged while Coffer has no model.
//
// Distillation merges the same lesson from two agents into one memory, and
// that takes Coffer's own model. With none set each agent's entry becomes its
// own memory, so the partition page says so quietly and links to where the
// model is chosen (Settings › General).
import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useOpenSettings } from "@/lib/settingsModal";

export function NoModelNotice() {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  return (
    <Alert variant="warning" data-testid="memory-no-model">
      <Info aria-hidden />
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <AlertTitle>{t("memory.noModel.title")}</AlertTitle>
          <AlertDescription>{t("memory.noModel.body")}</AlertDescription>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => openSettings("general")}>
          {t("memory.noModel.link")}
        </Button>
      </div>
    </Alert>
  );
}
