// src/components/secret/SecretPane.tsx — the open secret in the Secrets page's detail pane.
//
// The header carries the name (the label — without one, a readable default) and, under it, the
// description as text (nothing when there is none); the visible actions are Edit, which opens one
// dialog for the name, description and value, and Reveal value…, and the ⋯ menu holds Copy
// reference and Delete…. Under the header, the overview: the reference, where it lives, when it
// was last used and who uses it. The reference never changes, so editing a note moves nothing
// that cites it. Its dialogs are the Secrets page's own. No value is
// shown until Reveal is confirmed (spec web-ui "Manage stored secrets on the Secrets page").
import { useState } from "react";
import { KeyRound, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { SecretRef } from "@/lib/api/secret";
import { presenceAvailable } from "@/lib/tauri";
import { DeleteSecretDialog } from "./DeleteSecretDialog";
import { EditSecretDialog } from "./EditSecretDialog";
import { RevealSecretDialog } from "./RevealSecretDialog";
import { SecretOverview } from "./SecretOverview";
import { displayName, isMissingHere, referenceOf } from "./secretRows";

interface Props {
  row: SecretRef;
  onDeleted: () => void;
}

type Dialog = "edit" | "reveal" | "delete" | null;

export function SecretPane({ row, onDeleted }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);
  const inApp = presenceAvailable();
  const missing = isMissingHere(row);
  const reference = referenceOf(row);
  const name = displayName(row, t("secrets.unnamed"));
  const close = (open: boolean) => {
    if (!open) setDialog(null);
  };

  const copyReference = () =>
    void navigator.clipboard
      .writeText(reference)
      .then(() => toast.success(t("secrets.menu.copied", { reference })))
      .catch(() => toast.error(t("secrets.menu.copyFailed")));
  const actions: MenuAction[] = [
    { key: "copy", label: t("secrets.menu.copyRef", { reference }), onSelect: copyReference },
    {
      key: "delete",
      label: t("secrets.menu.delete"),
      destructive: true,
      // A ref cited but not stored has no value to delete.
      disabled: !row.present,
      separated: true,
      onSelect: () => setDialog("delete"),
    },
  ];

  return (
    <div className="space-y-[18px]">
      <header className="flex min-w-0 flex-wrap items-start gap-3">
        <span className="mt-1 inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <KeyRound className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-[12rem] flex-1 flex-col gap-0.5 pt-0.5">
          <h2 className="min-w-0 break-words text-lg font-semibold text-text">{name}</h2>
          {row.description ? (
            <p className="min-w-0 break-words text-xs text-text-muted" data-testid="secret-description">
              {row.description}
            </p>
          ) : null}
        </div>
        <span className="inline-flex shrink-0 items-center gap-2 pt-1">
          <Button size="sm" variant="outline" onClick={() => setDialog("edit")}>
            <Pencil aria-hidden />
            {t("common.edit")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={!inApp || missing}
            title={inApp ? undefined : t("secrets.menu.revealInApp")}
            onClick={() => setDialog("reveal")}
          >
            {inApp ? t("secrets.menu.reveal") : t("secrets.menu.revealInApp")}
          </Button>
          <ActionMenu label={t("secrets.menu.label", { name: row.ref })} actions={actions} />
        </span>
      </header>

      <div className="border-t border-border-subtle pt-5">
        <SecretOverview row={row} />
      </div>

      <EditSecretDialog row={dialog === "edit" ? row : null} onOpenChange={close} />
      <RevealSecretDialog row={dialog === "reveal" ? row : null} onOpenChange={close} />
      <DeleteSecretDialog
        row={dialog === "delete" ? row : null}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        onDeleted={onDeleted}
      />
    </div>
  );
}
