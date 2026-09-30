// src/components/providers/AddModelsStep.tsx — step 2 of Add: which of the listed models the provider offers.
//
// Nothing selected means every model the endpoint serves is offered (spec
// provider-switching "Curate the models a connection offers"). A local
// runtime's models show their context window and whether they call tools; the
// tool-capable ones start selected.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Checkbox } from "@/components/ui/checkbox";
import { MODALITIES, type Modality, type ProviderModel } from "@/lib/api/providers";
import { ChoiceChips } from "./ChoiceChips";

export interface CandidateModel extends ProviderModel {
  /** A local runtime's answer: false = cannot call tools. */
  tools?: boolean | null;
}

interface Props {
  models: CandidateModel[];
  selected: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
  /** Why nothing is listed, when the Test failed or the endpoint listed none. */
  emptyNote: string;
}

export function AddModelsStep({ models, selected, onChange, emptyNote }: Props) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState("");
  const [type, setType] = useState<Modality | "all">("all");
  const needle = query.trim().toLowerCase();
  const rows = models.filter(
    (m) =>
      (type === "all" || (m.modality ?? "text") === type) &&
      (!needle || m.id.toLowerCase().includes(needle)),
  );
  const number = new Intl.NumberFormat(i18n.language);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  if (models.length === 0) return <p className="text-sm text-text-muted">{emptyNote}</p>;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t("providers.add.models.search", { count: models.length })}
          ariaLabel={t("providers.models.search")}
          className="w-56"
        />
        <ChoiceChips
          label={t("providers.models.typeFilter")}
          value={type}
          options={[
            { value: "all" as const, label: t("providers.models.allTypes") },
            ...MODALITIES.filter((m) => models.some((x) => (x.modality ?? "text") === m)).map(
              (m) => ({
                value: m,
                label: t(`providers.modalities.${m}`),
              }),
            ),
          ]}
          onChange={setType}
        />
      </div>
      <p className="text-xs text-text-muted">
        {t("providers.add.models.count", { n: selected.size, count: models.length })}
      </p>
      <div className="flex max-h-72 flex-col overflow-y-auto rounded-xl border border-border">
        {rows.map((m) => (
          <label
            key={m.id}
            className="flex min-h-10 cursor-pointer items-center gap-3 px-3 py-1.5 hover:bg-surface-hover [&+&]:border-t [&+&]:border-border-subtle"
          >
            <Checkbox
              checked={selected.has(m.id)}
              onChange={() => toggle(m.id)}
              aria-label={m.id}
            />
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">{m.id}</span>
            {m.context_window ? (
              <span className="text-2xs text-text-muted">
                {t("providers.add.models.window", { tokens: number.format(m.context_window) })}
              </span>
            ) : null}
            {m.tools === false ? (
              <span className="text-2xs text-text-muted">{t("providers.add.models.noTools")}</span>
            ) : null}
            <span className="w-24 text-right text-2xs text-text-muted">
              {t(`providers.modalities.${m.modality ?? "text"}`)}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
