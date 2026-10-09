// src/components/providers/SetWindowDialog.tsx — the context window you set on one model of a provider.
//
// One field, in tokens ("128000", "128k", "1m"). What you set wins over what
// the endpoint reports and the bundled list; "Reset to default" (footer, left)
// drops it and appears only when a window of yours exists (spec
// provider-switching "Resolve each provider model's context window").
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
import type { ModelWindow } from "@/lib/api/providers";
import { parseWindow } from "@/lib/providers/window";

interface Props {
  model: string | null;
  current: ModelWindow | undefined;
  onClose: () => void;
  onSave: (tokens: number) => void;
  /** Drop your own window; offered only while one exists. */
  onReset: () => void;
}

export function SetWindowDialog({ model, current, onClose, onSave, onReset }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={model !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[440px]">
        {model !== null ? (
          <WindowForm
            key={model}
            model={model}
            current={current}
            onClose={onClose}
            onSave={onSave}
            onReset={onReset}
          />
        ) : (
          <DialogTitle className="sr-only">
            {t("providers.window.dialogTitle", { id: "" })}
          </DialogTitle>
        )}
      </DialogContent>
    </Dialog>
  );
}

function WindowForm({ model, current, onClose, onSave, onReset }: Props & { model: string }) {
  const { t } = useTranslation();
  const [text, setText] = useState(current?.tokens ? String(current.tokens) : "");
  const tokens = parseWindow(text);
  const invalid = text.trim() !== "" && tokens === null;

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("providers.window.dialogTitle", { id: model })}</DialogTitle>
        <DialogDescription>{t("providers.window.dialogBody")}</DialogDescription>
      </DialogHeader>
      <label className="flex flex-col gap-1 text-xs font-label text-text">
        <span>{t("providers.window.field")}</span>
        <Input
          inputMode="numeric"
          value={text}
          placeholder="128k"
          aria-invalid={invalid || undefined}
          onChange={(e) => setText(e.target.value)}
          className="font-mono"
        />
        <span className={invalid ? "text-danger" : "text-text-muted"}>
          {invalid ? t("providers.window.invalid") : t("providers.window.hint")}
        </span>
      </label>
      <DialogFooter>
        {current?.source === "user" ? (
          <Button
            variant="ghost"
            className="sm:mr-auto"
            onClick={() => {
              onReset();
              onClose();
            }}
          >
            {t("providers.window.reset")}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button
          disabled={tokens === null}
          onClick={() => {
            if (tokens === null) return;
            onSave(tokens);
            onClose();
          }}
        >
          {t("common.save")}
        </Button>
      </DialogFooter>
    </>
  );
}
