// src/components/custom-tools/ReimportDialog.tsx — Re-import (1060, the change preview): read the group's spec
// again (a file source asks for the file) and list what it would change before anything does — what will
// happen in words, the changes with a tick for each operation to add (writes start unticked), and the chosen
// change's spec text on the right. Nothing changes until Apply; unchanged tools keep their switch and reach.
import { useEffect, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { OpChip } from "@/components/change-preview/OpChip";
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
import { OP_ORDER } from "@/lib/changePreview/changeCounts";
import { defaultAdds, reimportItems, type ReimportItem } from "@/lib/customTools/reimport";
import { useApplyReimport, usePreviewReimport } from "@/lib/hooks/useCustomTools";
import { ReimportDetail } from "./ReimportDetail";
import { ReimportRow } from "./ReimportRow";
import { MAX_SPEC_BYTES } from "./SpecField";

interface Props {
  group: CustomToolGroup;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const LABEL = "text-2xs font-semibold uppercase tracking-wide text-text-subtle";

/** One "What will happen" sentence, led by the tool's name in bold. */
function Sentence({ item }: { item: ReimportItem }) {
  const names = item.newRequired ?? [];
  const key =
    item.op === "add"
      ? item.write
        ? "customTools.reimport.willAddWrite"
        : "customTools.reimport.willAddRead"
      : item.op === "remove"
        ? "customTools.reimport.willRemove"
        : names.length > 0
          ? "customTools.reimport.willRequire"
          : "customTools.reimport.willChange";
  return (
    <p>
      <Trans
        i18nKey={key}
        values={{ name: item.name, count: names.length, names: names.join(", ") }}
        components={{ b: <b className="font-semibold text-text" /> }}
      />
    </p>
  );
}

export function ReimportDialog({ group, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const preview = usePreviewReimport(group.name);
  const apply = useApplyReimport(group.name);
  const [document, setDocument] = useState<string | undefined>(undefined);
  const [tooLarge, setTooLarge] = useState(false);
  const [adds, setAdds] = useState<string[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const fromFile = group.source?.kind === "file";

  useEffect(() => {
    if (!open) return;
    preview.reset();
    apply.reset();
    setDocument(undefined);
    setTooLarge(false);
    setChosen(null);
    if (!fromFile) preview.mutate(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const p = preview.data;
  const items = p ? reimportItems(p, group) : [];
  useEffect(() => {
    setAdds(defaultAdds(items));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a new preview starts from its defaults
  }, [p]);
  const error = apply.error ?? preview.error;
  const count = items.filter((i) => i.op !== "add" || adds.includes(i.key as string)).length;
  const unchanged = p ? p.kept.length - p.changed.length : 0;
  const current = items.find((i) => i.id === chosen) ?? items[0];
  const location = group.source?.location ?? "";
  const versions = [group.source?.version, p?.version];
  const from =
    versions[0] && versions[1] && versions[0] !== versions[1]
      ? `${p?.title ?? group.source?.title ?? ""} ${versions[0]} → ${versions[1]}`.trim()
      : [p?.title, p?.version].filter(Boolean).join(" ");
  const file = location.split("/").pop() || location;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[1060px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("customTools.reimport.title", { name: group.name })}</DialogTitle>
          <DialogDescription>
            {[
              t(fromFile ? "customTools.reimport.subtitleFile" : "customTools.reimport.subtitle", {
                location,
              }),
              p && from ? from : null,
            ]
              .filter(Boolean)
              .join(" · ")}
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
                const picked = e.target.files?.[0];
                e.target.value = "";
                if (!picked) return;
                if (picked.size > MAX_SPEC_BYTES) return setTooLarge(true);
                setTooLarge(false);
                void picked.text().then((text) => {
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
          <div className="flex flex-col gap-3.5" data-testid="reimport-preview">
            {items.length === 0 ? (
              <p className="text-sm text-text-muted">{t("customTools.reimport.noChange")}</p>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-label">
                    {t("customTools.reimport.summary", { count: items.length, name: group.name })}
                  </span>
                  {OP_ORDER.map((op) => {
                    const n = items.filter((i) => i.op === op).length;
                    return n > 0 ? (
                      <span key={op} className="inline-flex items-center gap-1.5">
                        <OpChip op={op} />
                        <span className="text-xs text-text-muted">{n}</span>
                      </span>
                    ) : null;
                  })}
                </div>
                <div className="grid grid-cols-[330px_minmax(0,1fr)] items-start gap-5">
                  <div className="flex min-w-0 flex-col gap-3">
                    <section className="flex flex-col gap-1.5 rounded-lg bg-surface-sunken p-3">
                      <span className={LABEL}>{t("changePreview.whatWillHappen")}</span>
                      <div className="flex flex-col gap-1.5 text-xs leading-[1.45] text-text-muted">
                        {items.map((item) => (
                          <Sentence key={item.id} item={item} />
                        ))}
                      </div>
                    </section>
                    <section className="flex flex-col gap-1">
                      <span className={LABEL}>
                        {t("changePreview.changesHeading", { count: items.length })}
                      </span>
                      {items.map((item) => (
                        <ReimportRow
                          key={item.id}
                          item={item}
                          selected={current?.id === item.id}
                          ticked={adds.includes(item.key ?? "")}
                          onTick={(on) =>
                            setAdds(
                              on
                                ? [...adds, item.key as string]
                                : adds.filter((k) => k !== item.key),
                            )
                          }
                          onSelect={() => setChosen(item.id)}
                        />
                      ))}
                    </section>
                  </div>
                  <div className="min-w-0">
                    {current ? <ReimportDetail item={current} file={file} /> : null}
                  </div>
                </div>
              </>
            )}
          </div>
        ) : null}
        {tooLarge || error ? (
          <div role="alert" className="flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
            <span>{tooLarge ? t("customTools.import.tooLarge") : translateApiError(t, error)}</span>
          </div>
        ) : null}
        <DialogFooter className="sm:items-center">
          {p ? (
            <span className="mr-auto min-w-0 text-xs text-text-muted">
              {t("customTools.reimport.kept", { count: unchanged })}
            </span>
          ) : null}
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={!p || count === 0 || apply.isPending}
            onClick={() =>
              apply.mutate({ add: adds, document }, { onSuccess: () => onOpenChange(false) })
            }
          >
            {apply.error ? t("common.retry") : t("customTools.reimport.apply", { count })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
