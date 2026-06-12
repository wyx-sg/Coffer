// components/chat/ChatEmptyState.tsx
// Shown in the message thread when no model is configured.
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function ChatEmptyState() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-12 text-center">
      <MessageSquare
        className="size-12 text-muted-foreground/40"
        strokeWidth={1.25}
        aria-hidden
      />
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">{t("chat.emptyState.title")}</h2>
        <p className="max-w-xs text-sm text-muted-foreground">
          {t("chat.emptyState.body")}
        </p>
      </div>
      <Button asChild>
        <Link to="/settings/models">{t("chat.emptyState.cta")}</Link>
      </Button>
    </div>
  );
}
