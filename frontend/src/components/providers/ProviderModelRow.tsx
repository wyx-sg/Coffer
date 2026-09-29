// src/components/providers/ProviderModelRow.tsx — one model on the Models tab: switch, id, what uses it, its type.
import type { Modality } from "@/lib/api/providers";
import { useTranslation } from "react-i18next";

import { Switch } from "@/components/ui/switch";
import { ModalitySelect } from "./ModalitySelect";

interface Props {
  id: string;
  on: boolean;
  modality: Modality;
  /** What uses this model: "Coffer's engine", "Codex default"… */
  tags: string[];
  disabled: boolean;
  onToggle: () => void;
  onModality: (m: Modality) => void;
}

export function ProviderModelRow({
  id,
  on,
  modality,
  tags,
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
      <ModalitySelect value={modality} onChange={onModality} disabled={disabled} label={id} />
    </div>
  );
}
