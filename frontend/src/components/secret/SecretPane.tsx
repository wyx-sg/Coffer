// src/components/secret/SecretPane.tsx — the open secret in the Secrets page's detail pane.
//
// The header carries the name (the label, edited in place — empty falls back to a readable default)
// and the description, also in place; the visible actions are Replace value… and Reveal value…, and
// the ⋯ menu holds Copy reference and Delete…. Two path tabs: Overview (reference, where it lives,
// who uses it) and Usage (where this Mac handed the value out). The reference never changes, so
// editing a note moves nothing that cites it. Its dialogs are the Secrets page's own. No value is
// shown until Reveal is confirmed (spec web-ui "Manage stored secrets on the Secrets page").
import { useState } from "react";
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import type { SecretRef } from "@/lib/api/secret";
import { useDetailTab } from "@/lib/detailTabs";
import { presenceAvailable } from "@/lib/tauri";
import { DeleteSecretDialog } from "./DeleteSecretDialog";
import { ReplaceSecretDialog } from "./ReplaceSecretDialog";
import { RevealSecretDialog } from "./RevealSecretDialog";
import { SecretNoteField } from "./SecretNoteField";
import { SecretOverview } from "./SecretOverview";
import { SecretRecentUses } from "./SecretRecentUses";
import { displayName, isMissingHere, referenceOf } from "./secretRows";

const SECRET_TABS = ["overview", "usage"] as const;

interface Props {
  row: SecretRef;
  /** The pane's bare address (`/secrets/<ref>`); a tab is a segment under it. */
  basePath: string;
  onDeleted: () => void;
}

type Dialog = "replace" | "reveal" | "delete" | null;

export function SecretPane({ row, basePath, onDeleted }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [tab, setTab] = useDetailTab(SECRET_TABS, "overview", basePath);
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
        {/* The name keeps room to be read and edited; on a narrow pane the actions wrap below it. */}
        <div className="flex min-w-[12rem] flex-1 flex-col gap-0.5">
          <SecretNoteField
            row={row}
            field="label"
            placeholder={name}
            className="text-lg font-semibold"
          />
          <SecretNoteField
            row={row}
            field="description"
            placeholder={t("secrets.detail.descriptionPlaceholder")}
            className="text-xs text-text-muted"
          />
        </div>
        <span className="inline-flex shrink-0 items-center gap-2 pt-1">
          <Button size="sm" variant="outline" onClick={() => setDialog("replace")}>
            {missing ? t("secrets.row.addValue") : t("secrets.menu.replace")}
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

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("secrets.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="usage">{t("secrets.tabs.usage")}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="pt-5">
          <SecretOverview row={row} />
        </TabsContent>
        <TabsContent value="usage" className="pt-5">
          <SecretRecentUses secretRef={row.ref} />
        </TabsContent>
      </Tabs>

      <ReplaceSecretDialog row={dialog === "replace" ? row : null} onOpenChange={close} />
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
