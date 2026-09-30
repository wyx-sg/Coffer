// src/components/custom-tools/ReimportDialog.tsx — Re-import: read the group's spec again (a file source
// asks for the file) and list the changes first — operations to add (reads become tools, on; writes
// are listed but not ticked), tools the spec changed, tools it dropped. Nothing changes until Apply;
// unchanged tools keep their switch and reach.
import { useEffect, useRef, useState } from "react";
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
import type { CustomToolGroup } from "@/lib/api/customTools";
import { operationChangesData } from "@/lib/customTools/operations";
import { useApplyReimport, usePreviewReimport } from "@/lib/hooks/useCustomTools";
import { ReimportRow } from "./ReimportRow";
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
  const [tooLarge, setTooLarge] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const fromFile = group.source?.kind === "file";

  useEffect(() => {
    if (!open) return;
    preview.reset();
    apply.reset();
    setDocument(undefined);
    setTooLarge(false);
    if (!fromFile) preview.mutate(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const p = preview.data;
  const error = apply.error ?? preview.error;
  const tools = new Map(group.tools.map((tool) => [tool.name, tool]));
  const reads = p ? p.added.filter((op) => !operationChangesData(op)).map((op) => op.key) : [];
  const changed = p?.changed ?? [];
  const count = p ? p.added.length + changed.length + p.removed.length : 0;
  const unchanged = p ? p.kept.length - changed.length : 0;
  const versions = [group.source?.title ?? p?.title, group.source?.version, p?.version];
  const from =
    versions[1] && versions[2] && versions[1] !== versions[2]
      ? `${versions[0] ?? ""} ${versions[1]} → ${versions[2]}`.trim()
      : [p?.title, p?.version].filter(Boolean).join(" ");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[620px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("customTools.reimport.title", { name: group.name })}</DialogTitle>
          <DialogDescription>
            {t(fromFile ? "customTools.reimport.subtitleFile" : "customTools.reimport.subtitle", {
              location: group.source?.location ?? "",
            })}
          </DialogDescription>
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
                  preview.mutate(text);
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
            {count === 0 ? (
              <p className="text-sm text-text-muted">{t("customTools.reimport.noChange")}</p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <div className="bg-surface-sunken px-2.5 py-2 text-xs font-semibold">
                  {[t("customTools.reimport.changes", { count }), from].filter(Boolean).join(" · ")}
                </div>
                {p.added.map((op) => (
                  <ReimportRow
                    key={op.key}
                    kind="add"
                    name={op.tool.name}
                    request={`${op.tool.method ?? "GET"} ${op.tool.path}`}
                    note={t(
                      operationChangesData(op)
                        ? "customTools.reimport.addWrite"
                        : "customTools.reimport.addRead",
                    )}
                  />
                ))}
                {changed.map((c) => (
                  <ReimportRow
                    key={c.name}
                    kind="change"
                    name={c.name}
                    request={`${c.method} ${c.path}`}
                    note={
                      c.new_required.length > 0
                        ? t("customTools.reimport.newRequired", {
                            count: c.new_required.length,
                            names: c.new_required.join(", "),
                          })
                        : t("customTools.reimport.requestChanged")
                    }
                  />
                ))}
                {p.removed.map((name) => {
                  const tool = tools.get(name);
                  return (
                    <ReimportRow
                      key={name}
                      kind="remove"
                      name={name}
                      request={tool ? `${tool.method} ${tool.path}` : ""}
                      note={t("customTools.reimport.gone")}
                    />
                  );
                })}
              </div>
            )}
            <p className="text-xs text-text-muted">
              {t("customTools.reimport.kept", { count: unchanged })}
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={!p || count === 0 || apply.isPending}
            onClick={() =>
              apply.mutate({ add: reads, document }, { onSuccess: () => onOpenChange(false) })
            }
          >
            {t("customTools.reimport.apply", { count })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
