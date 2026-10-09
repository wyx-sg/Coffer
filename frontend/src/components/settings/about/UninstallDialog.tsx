// src/components/settings/about/UninstallDialog.tsx
//
// "Uninstall Coffer?" (spec web-ui "Offer uninstall on Settings › About";
// canvas 1.4.28–1.4.29), the shell's one confirmation dialog: what goes, what
// stays, and an unticked Also delete my data. Ticking it turns the note into a
// danger note, offers Back up the master key first and renames the button —
// the shell then asks for Touch ID before anything is sent. While it runs the
// dialog cannot be left; a failure stays in it. When the daemon has answered,
// the steps it took are shown while the app moves itself to the Trash and quits.
import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Check, Minus, Trash2, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog, ConfirmFacts } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { uninstallCoffer, type UninstallReport } from "@/lib/shellUninstall";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Opened by `coffer uninstall --delete-data`: the box starts ticked. */
  deleteFirst?: boolean;
}

export function UninstallDialog({ open, onOpenChange, deleteFirst = false }: Props) {
  const { t } = useTranslation();
  const [deleteData, setDeleteData] = useState(deleteFirst);
  const [report, setReport] = useState<UninstallReport | null>(null);

  if (report) return <Uninstalled report={report} />;

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setDeleteData(deleteFirst);
      }}
      title={t("settings.about.uninstall.dialog.title")}
      description={t("settings.about.uninstall.dialog.body")}
      confirmLabel={
        deleteData
          ? t("settings.about.uninstall.dialog.confirmDelete")
          : t("settings.about.uninstall.dialog.confirm")
      }
      confirmIcon={<Trash2 aria-hidden />}
      pendingLabel={t("settings.about.uninstall.dialog.pending")}
      errorTitle={t("settings.about.uninstall.dialog.failed")}
      onConfirm={async () => setReport(await uninstallCoffer(deleteData))}
    >
      <ConfirmFacts
        items={[
          {
            label: t("settings.about.uninstall.dialog.removes"),
            value: t("settings.about.uninstall.dialog.removesValue"),
          },
          {
            label: t("settings.about.uninstall.dialog.keeps"),
            value: deleteData
              ? t("settings.about.uninstall.dialog.keepsNothing")
              : t("settings.about.uninstall.dialog.keepsValue"),
          },
        ]}
      />
      <label className="flex items-start gap-2.5 text-sm text-text">
        <Checkbox
          className="mt-0.5"
          checked={deleteData}
          onChange={(e) => setDeleteData(e.target.checked)}
        />
        <span className="flex flex-col gap-0.5">
          <span>{t("settings.about.uninstall.dialog.deleteData")}</span>
          <span className="text-xs text-text-muted">
            {t("settings.about.uninstall.dialog.deleteDataHelp")}
          </span>
        </span>
      </label>
      {deleteData ? (
        <Alert variant="destructive">
          <AlertTriangle aria-hidden />
          <div className="flex flex-col gap-1">
            <span className="text-sm font-label text-text">
              {t("settings.about.uninstall.dialog.dangerTitle")}
            </span>
            <span>{t("settings.about.uninstall.dialog.danger")}</span>
            <Link
              to="/settings/security?backup=1"
              className="w-fit text-xs font-label text-accent hover:underline"
              onClick={() => onOpenChange(false)}
            >
              {t("settings.about.uninstall.dialog.backup")}
            </Link>
          </div>
        </Alert>
      ) : null}
    </ConfirmDialog>
  );
}

const MARKS = { done: Check, nothing: Minus, failed: X } as const;

/** What the uninstall did, shown while the app quits. Nothing to press. */
function Uninstalled({ report }: { report: UninstallReport }) {
  const { t } = useTranslation();
  return (
    <Dialog open>
      <DialogContent className="max-w-[420px]" hideClose>
        <DialogHeader>
          <DialogTitle>{t("settings.about.uninstall.done.title")}</DialogTitle>
          <DialogDescription>
            {report.deletes_data
              ? t("settings.about.uninstall.done.bodyDeleted")
              : t("settings.about.uninstall.done.body")}
          </DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-1.5 text-sm text-text" data-testid="uninstall-steps">
          {report.steps.map((step) => {
            const Mark = MARKS[step.outcome];
            return (
              <li key={step.key} className="flex items-start gap-2">
                <Mark
                  aria-hidden
                  className={
                    step.outcome === "failed"
                      ? "mt-0.5 size-4 shrink-0 text-danger"
                      : "mt-0.5 size-4 shrink-0 text-text-muted"
                  }
                />
                <span className="flex min-w-0 flex-col">
                  <span>
                    {t(`settings.about.uninstall.steps.${step.key}`, { defaultValue: step.key })}
                    {" · "}
                    <span className="text-text-muted">
                      {t(`settings.about.uninstall.outcome.${step.outcome}`)}
                    </span>
                  </span>
                  {step.outcome === "failed" && step.detail ? (
                    <span className="break-words text-xs text-text-muted">{step.detail}</span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
