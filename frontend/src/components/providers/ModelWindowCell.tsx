// src/components/providers/ModelWindowCell.tsx — one model's context window on a provider, with where it came from.
//
// "1M · Bundled" (tokens, compact), clicking it opens the window dialog. A
// model nothing knows the window of reads "—" with Set window…: no window is
// written for it, none is guessed (spec provider-switching "Resolve each
// provider model's context window").
import { useTranslation } from "react-i18next";

import type { ModelWindow } from "@/lib/api/providers";
import { formatWindow } from "@/lib/providers/window";

const LINK =
  "text-xs font-label text-accent-text outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus-ring";

interface Props {
  id: string;
  window: ModelWindow | undefined;
  onEdit: () => void;
  disabled?: boolean;
}

export function ModelWindowCell({ id, window, onEdit, disabled }: Props) {
  const { t } = useTranslation();
  if (!window?.tokens || !window.source) {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-text-muted">
        <span aria-label={t("providers.window.noneAria", { id })}>—</span>
        <button type="button" className={LINK} onClick={onEdit} disabled={disabled}>
          {t("providers.window.set")}
        </button>
      </span>
    );
  }
  const tokens = formatWindow(window.tokens);
  return (
    <button
      type="button"
      onClick={onEdit}
      disabled={disabled}
      aria-label={t("providers.window.editAria", { id, tokens })}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm text-xs outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus-ring"
    >
      <span className="font-mono text-text">{tokens}</span>
      <span className="text-text-muted">{t(`providers.window.source.${window.source}`)}</span>
    </button>
  );
}
