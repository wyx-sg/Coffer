// frontend/src/components/chat/RenameConversationDialog.tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import { useRenameConversation } from "@/lib/hooks/useChat";

export function RenameConversationDialog({
  id,
  currentTitle,
  open,
  onOpenChange,
}: {
  id: string;
  currentTitle: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const rename = useRenameConversation();
  const [title, setTitle] = useState(currentTitle);

  useEffect(() => {
    if (open) setTitle(currentTitle);
  }, [open, currentTitle]);

  const submit = () => {
    const trimmed = title.trim();
    if (!trimmed) return;
    rename.mutate({ id, body: { title: trimmed } }, { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("chat.rename.title")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="chat-rename-input">{t("chat.rename.label")}</Label>
          <Input
            id="chat-rename-input"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            autoFocus
          />
        </div>
        {rename.error ? (
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{translateApiError(t, rename.error)}</span>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!title.trim() || rename.isPending}>
            {rename.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
