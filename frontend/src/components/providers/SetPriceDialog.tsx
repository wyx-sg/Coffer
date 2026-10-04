// src/components/providers/SetPriceDialog.tsx — the price you set on one model of a provider.
//
// Input and output per 1M tokens are required; cache reads and 5-minute cache
// writes are optional (left out, they are charged at the input rate, so an
// estimate errs high). What you set wins over the provider's API and the
// bundled list; "Reset to default" (footer, left) drops it and appears only
// when a price of yours exists.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { CuratedPrice, ModelPrice } from "@/lib/api/providers";

type Field = "input" | "output" | "cache_read" | "cache_write_5m";
const FIELDS: readonly Field[] = ["input", "output", "cache_read", "cache_write_5m"];
const REQUIRED = new Set<Field>(["input", "output"]);

function initial(price: ModelPrice | undefined): Record<Field, string> {
  const pick = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return {
    input: pick(price?.input),
    output: pick(price?.output),
    cache_read: pick(price?.cache_read),
    cache_write_5m: pick(price?.cache_write_5m),
  };
}

interface Props {
  model: string | null;
  current: ModelPrice | undefined;
  onClose: () => void;
  onSave: (price: CuratedPrice) => void;
  /** Drop your own price; offered only while one exists. */
  onReset?: () => void;
}

export function SetPriceDialog({ model, current, onClose, onSave, onReset }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={model !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[480px]">
        {model !== null ? (
          <PriceForm
            key={model}
            model={model}
            current={current}
            onClose={onClose}
            onSave={onSave}
            onReset={onReset}
          />
        ) : (
          <DialogTitle className="sr-only">
            {t("providers.prices.dialogTitle", { id: "" })}
          </DialogTitle>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PriceForm({ model, current, onClose, onSave, onReset }: Props & { model: string }) {
  const { t } = useTranslation();
  const [values, setValues] = useState(() => initial(current));
  const parsed = Object.fromEntries(
    FIELDS.map((f) => [f, values[f].trim() === "" ? null : Number(values[f])]),
  ) as Record<Field, number | null>;
  const invalid = FIELDS.some((f) => {
    const v = parsed[f];
    return (REQUIRED.has(f) && v === null) || (v !== null && (!Number.isFinite(v) || v < 0));
  });

  const save = () => {
    if (invalid) return;
    const price: CuratedPrice = { input: parsed.input ?? 0, output: parsed.output ?? 0 };
    if (parsed.cache_read !== null) price.cache_read = parsed.cache_read;
    if (parsed.cache_write_5m !== null) price.cache_write_5m = parsed.cache_write_5m;
    onSave(price);
    onClose();
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("providers.prices.dialogTitle", { id: model })}</DialogTitle>
        <DialogDescription>{t("providers.prices.dialogBody")}</DialogDescription>
      </DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        {FIELDS.map((f) => (
          <label key={f} className="flex flex-col gap-1 text-xs font-label text-text">
            <span>
              {t(`providers.prices.fields.${f}`)}
              {REQUIRED.has(f) ? <span aria-hidden> *</span> : null}
            </span>
            <span className="relative block">
              <span
                aria-hidden
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 font-mono text-xs text-text-muted"
              >
                $
              </span>
              <Input
                inputMode="decimal"
                value={values[f]}
                placeholder={REQUIRED.has(f) ? "0.00" : t("providers.prices.optional")}
                onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
                className="pl-6 pr-10 font-mono"
              />
              <span
                aria-hidden
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 font-mono text-xs text-text-muted"
              >
                / 1M
              </span>
            </span>
          </label>
        ))}
      </div>
      <p className="text-xs text-text-muted">{t("providers.prices.perMillion")}</p>
      <DialogFooter>
        {current?.source === "user" && onReset ? (
          <Button
            variant="ghost"
            className="sm:mr-auto"
            onClick={() => {
              onReset();
              onClose();
            }}
          >
            {t("providers.prices.reset")}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button onClick={save} disabled={invalid}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </>
  );
}
