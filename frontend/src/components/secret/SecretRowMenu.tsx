// src/components/secret/SecretRowMenu.tsx — a secret's ⋯ menu.
//
// Replace value… (not on a secret missing on this Mac: the row's Add value
// button is that) · Reveal value…
// · Copy reference (<reference>) · Show in Activity · Delete….
// Reveal exists only in the desktop app (spec secret "Release plaintext
// only to a present human in the desktop app"): a browser shows it disabled,
// naming the app. Delete stays offered while something uses the secret: the
// dialog it opens then says what still uses it instead of deleting (spec
// secret "Refuse to delete a secret still in use").
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { SecretRef } from "@/lib/api/secret";
import { presenceAvailable } from "@/lib/tauri";
import { displayName, isMissingHere, referenceOf } from "./secretRows";

export type SecretRowAction = "replace" | "reveal" | "delete";

interface Props {
  row: SecretRef;
  onAction: (action: SecretRowAction, row: SecretRef) => void;
}

export function SecretRowMenu({ row, onAction }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const inApp = presenceAvailable();
  const reference = referenceOf(row);
  const missing = isMissingHere(row);

  const copyReference = () =>
    void navigator.clipboard
      .writeText(reference)
      .then(() => toast.success(t("secrets.menu.copied", { reference })))
      .catch(() => toast.error(t("secrets.menu.copyFailed")));

  const actions: MenuAction[] = [
    // A secret missing on this Mac has the row's own Add value button.
    ...(missing
      ? []
      : [
          {
            key: "replace",
            label: t("secrets.menu.replace"),
            onSelect: () => onAction("replace", row),
          },
        ]),
    {
      key: "reveal",
      label: inApp ? t("secrets.menu.reveal") : t("secrets.menu.revealInApp"),
      // A value this Mac cannot open cannot be shown either.
      disabled: !inApp || missing,
      onSelect: () => onAction("reveal", row),
    },
    { key: "copy", label: t("secrets.menu.copyRef", { reference }), onSelect: copyReference },
    {
      key: "activity",
      label: t("secrets.menu.activity"),
      onSelect: () => navigate("/activity?tab=changes"),
    },
    {
      key: "delete",
      label: t("secrets.menu.delete"),
      destructive: true,
      // A ref cited but not stored has no value to delete.
      disabled: !row.present,
      separated: true,
      onSelect: () => onAction("delete", row),
    },
  ];
  return (
    <ActionMenu label={t("secrets.menu.label", { name: displayName(row) })} actions={actions} />
  );
}
