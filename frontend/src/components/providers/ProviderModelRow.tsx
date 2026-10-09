// src/components/providers/ProviderModelRow.tsx — one model in the Models section, a table row: select box, switch, id (never wrapped) with what uses it, its price, its context window, its type.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
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
  /** The model's context window and where it came from (ModelWindowCell). */
  window?: ReactNode;
  disabled: boolean;
  selected: boolean;
  onSelect: () => void;
  onToggle: () => void;
  onModality: (m: Modality) => void;
}

export function ProviderModelRow({
  id,
  on,
  modality,
  tags,
  price,
  window,
  disabled,
  selected,
  onSelect,
  onToggle,
  onModality,
}: Props) {
  const { t } = useTranslation();
  return (
    <tr data-testid="model-row" className="border-b border-border-subtle last:border-b-0">
      <td className="py-2 pl-4 pr-1 align-middle">
        <Checkbox
          checked={selected}
          onChange={onSelect}
          aria-label={t("agents.kindTab.selectRow", { name: id })}
        />
      </td>
      <td className="px-2 py-2 align-middle">
        <Switch
          checked={on}
          onCheckedChange={onToggle}
          disabled={disabled}
          aria-label={t("providers.models.offered", { id })}
        />
      </td>
      <td className="min-w-0 px-2 py-2 align-middle">
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
      </td>
      <td className="px-2 py-2 align-middle">{price}</td>
      <td className="px-2 py-2 align-middle">{window}</td>
      <td className="py-2 pl-2 pr-4 align-middle">
        <ModalitySelect value={modality} onChange={onModality} disabled={disabled} label={id} />
      </td>
    </tr>
  );
}
