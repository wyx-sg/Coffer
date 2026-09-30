// src/components/custom-tools/ReimportDialog.tsx — Re-import: read the group's spec again (a file source
// asks for the file), preview the operations it would add and the tools it would remove, and change
// nothing until Confirm. Kept tools keep their switch and reach override.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { useApplyReimport, usePreviewReimport } from "@/lib/hooks/useCustomTools";
import { MAX_SPEC_BYTES } from "./SpecField";

interface Props {
  group: CustomToolGroup;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReimportDialog({ group, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const preview = usePreviewReimport(group.name);
  const apply = useApplyReimport(group.name);
  const [document, setDocument] = useState<string | undefined>(undefined);
  const [add, setAdd] = useState<string[]>([]);
  const [tooLarge, setTooLarge] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const fromFile = group.source?.kind === "file";

  const run = (doc?: string) =>
    preview.mutate(doc, {
      onSuccess: (p) =>
        setAdd(p.added.filter((op) => (op.tool.method ?? "GET") === "GET").map((op) => op.key)),
    });

  useEffect(() => {
    if (!open) return;
    preview.reset();
    apply.reset();
    setDocument(undefined);
    setAdd([]);
    setTooLarge(false);
    if (!fromFile) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const p = preview.data;
  const error = apply.error ?? preview.error;
  const onConfirm = () => apply.mutate({ add, document }, { onSuccess: () => onOpenChange(false) });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[520px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("customTools.reimport.title", { name: group.name })}</DialogTitle>
          <DialogDescription>{t("customTools.reimport.subtitle")}</DialogDescription>
        </DialogHeader>
        {fromFile ? (
          <div className="flex items-center gap-2">
            <input
              ref={fileInput}
              type="file"
              accept=".json,.yaml,.yml,application/json,application/yaml"
              className="sr-only"
              aria-label={t("customTools.reimport.file")}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                if (file.size > MAX_SPEC_BYTES) return setTooLarge(true);
                setTooLarge(false);
                void file.text().then((text) => {
                  setDocument(text);
                  run(text);
                });
              }}
            />
            <Button variant="outline" onClick={() => fileInput.current?.click()}>
              {t("customTools.import.browse")}
            </Button>
            <span className="text-xs text-text-muted">{t("customTools.reimport.fileHelp")}</span>
          </div>
        ) : null}
        {preview.isPending ? (
          <p className="text-sm text-text-muted">{t("customTools.reimport.reading")}</p>
        ) : null}
        {p ? (
          <div className="flex flex-col gap-2" data-testid="reimport-preview">
            {p.added.length === 0 && p.removed.length === 0 ? (
              <p className="text-sm text-text-muted">{t("customTools.reimport.noChange")}</p>
            ) : null}
            <ul className="divide-y divide-border-subtle rounded-lg border border-border-subtle empty:hidden">
              {p.added.map((op) => (
                <li key={op.key}>
                  <label className="flex min-h-row cursor-pointer items-center gap-3 px-3 py-1.5">
                    <Checkbox
                      checked={add.includes(op.key)}
                      aria-label={t("customTools.reimport.addOp", { name: op.tool.name })}
                      onChange={(e) =>
                        setAdd(
                          e.target.checked ? [...add, op.key] : add.filter((k) => k !== op.key),
                        )
                      }
                    />
                    <span className="text-success">+</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-xs">{op.key}</span>
                    {(op.tool.method ?? "GET") !== "GET" ? (
                      <Badge variant="secondary">{t("customTools.tools.changesData")}</Badge>
                    ) : null}
                  </label>
                </li>
              ))}
              {p.removed.map((name) => (
                <li key={name} className="flex min-h-row items-center gap-3 px-3 py-1.5">
                  <span className="w-[15px]" />
                  <span className="text-danger">−</span>
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">
                    {t("customTools.reimport.removeTool", { name })}
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-text-muted">
              {t("customTools.reimport.kept", { count: p.kept.length })}
            </p>
          </div>
        ) : null}
        {tooLarge || error ? (
          <div role="alert" className="flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
            <span>{tooLarge ? t("customTools.import.tooLarge") : translateApiError(t, error)}</span>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!p || apply.isPending} onClick={onConfirm}>
            {t("customTools.reimport.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
