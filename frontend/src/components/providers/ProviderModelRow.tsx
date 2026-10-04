// src/components/providers/ProviderModelRow.tsx — one model in the Models section: switch, id (never wrapped), what uses it, its price, its type.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Switch } from "@/components/ui/switch";
import type { Modality } from "@/lib/api/providers";
import { cn } from "@/lib/utils";
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
    <div
      data-testid="model-row"
      className="grid min-h-row grid-cols-[auto_minmax(0,1fr)_auto_120px] items-center gap-3 px-3.5 py-2"
    >
      <Switch
        checked={on}
        onCheckedChange={onToggle}
        disabled={disabled}
        aria-label={t("providers.models.offered", { id })}
      />
      <span className="flex min-w-0 items-center gap-2">
        <span
          className={cn(
            "shrink-0 whitespace-nowrap font-mono text-xs",
            on ? "text-text" : "text-text-subtle",
          )}
        >
          {id}
        </span>
        {tags.map((tag) => (
          <span
            key={tag}
            className="block h-[18px] min-w-0 truncate whitespace-nowrap rounded-sm bg-chip px-1.5 text-2xs leading-[18px] font-label text-text-muted"
          >
            {tag}
          </span>
        ))}
      </span>
      <span className="justify-self-end">{price}</span>
      <ModalitySelect value={modality} onChange={onModality} disabled={disabled} label={id} />
    </div>
  );
}
