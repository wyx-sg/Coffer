// src/components/credentials/SecretRowMenu.tsx — a secret's ⋯ menu.
//
// Replace value… · Reveal value… · Copy reference · Show in Activity · Delete….
// Reveal exists only in the desktop app (spec credentials "Release plaintext
// only to a present human in the desktop app"): a browser shows it disabled,
// naming the app. Delete stays offered while something uses the secret: the
// dialog it opens then says what still uses it instead of deleting (spec
// credentials "Refuse to delete a credential still in use").
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { CredentialRef } from "@/lib/api/credentials";
import { presenceAvailable } from "@/lib/tauri";
import { displayName, referenceOf } from "./secretRows";

export type SecretRowAction = "replace" | "reveal" | "delete";

interface Props {
  row: CredentialRef;
  onAction: (action: SecretRowAction, row: CredentialRef) => void;
}

export function SecretRowMenu({ row, onAction }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const inApp = presenceAvailable();
  const reference = referenceOf(row);

  const copyReference = () =>
    void navigator.clipboard
      .writeText(reference)
      .then(() => toast.success(t("secrets.menu.copied", { reference })))
      .catch(() => toast.error(t("secrets.menu.copyFailed")));

  const actions: MenuAction[] = [
    {
      key: "replace",
      label: row.present ? t("secrets.menu.replace") : t("secrets.menu.store"),
      onSelect: () => onAction("replace", row),
    },
    {
      key: "reveal",
      label: inApp ? t("secrets.menu.reveal") : t("secrets.menu.revealInApp"),
      disabled: !inApp || !row.present,
      onSelect: () => onAction("reveal", row),
    },
    { key: "copy", label: t("secrets.menu.copyRef"), onSelect: copyReference },
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
