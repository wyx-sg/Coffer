// frontend/src/kinds/mcp/McpServerDeleteDialog.tsx
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  name: string;
  open: boolean;
  isPending: boolean;
  /** Mutation error to surface inline; the dialog stays open on failure. */
  error?: unknown;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function McpServerDeleteDialog({
  name,
  open,
  isPending,
  error,
  onOpenChange,
  onConfirm,
}: Props) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("mcp.server.deleteConfirmTitle", { name })}</DialogTitle>
          <DialogDescription>{t("mcp.server.deleteConfirmBody")}</DialogDescription>
        </DialogHeader>
        {error ? (
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{translateApiError(t, error)}</span>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={isPending}>
            {isPending ? t("common.deleting") : t("common.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
