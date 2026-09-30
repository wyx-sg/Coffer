// src/components/providers/ProviderModelRow.tsx — one model in the Models section: switch, id, what uses it, its price, its type.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Switch } from "@/components/ui/switch";
import type { Modality } from "@/lib/api/providers";
import { ModalitySelect } from "./ModalitySelect";

interface Props {
  id: string;
  on: boolean;
  modality: Modality;
  /** What uses this model: "Coffer's engine", "Codex default"… */
  tags: string[];
  /** The model's price and where it came from (ModelPriceCell). */
  price?: ReactNode;
  disabled: boolean;
  onToggle: () => void;
  onModality: (m: Modality) => void;
}

export function ProviderModelRow({
  id,
  on,
  modality,
  tags,
  price,
  disabled,
  onToggle,
  onModality,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-11 items-center gap-3 px-3 py-1.5 [&+&]:border-t [&+&]:border-border-subtle">
      <Switch
        checked={on}
        onCheckedChange={onToggle}
        disabled={disabled}
        aria-label={t("providers.models.offered", { id })}
      />
      <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <span className="truncate font-mono text-xs text-text">{id}</span>
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex h-[18px] items-center whitespace-nowrap rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted"
          >
            {tag}
          </span>
        ))}
      </span>
      {price ? <span className="shrink-0">{price}</span> : null}
      <ModalitySelect value={modality} onChange={onModality} disabled={disabled} label={id} />
    </div>
  );
}
