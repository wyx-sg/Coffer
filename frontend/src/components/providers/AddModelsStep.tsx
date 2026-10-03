// src/components/providers/AddModelsStep.tsx — step 2 of Add: which of the listed models the provider offers.
//
// Nothing selected means every model the endpoint serves is offered (spec
// provider-switching "Curate the models a connection offers"). A local
// runtime's models show their context window and whether they call tools; the
// tool-capable ones start selected. Search and Type work as on the Models
// section; the list shows a page of rows and "Show N more".
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import { MODALITIES, type Modality, type ProviderModel } from "@/lib/api/providers";
import { ModelsToolbar } from "./ModelsToolbar";

const PAGE = 9;

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

/** 400000 → "400k", 1048576 → "1M": a context window as people say it. */
function windowLabel(tokens: number): string {
  if (tokens >= 1_000_000) return `${Math.round(tokens / 100_000) / 10}M`.replace(".0M", "M");
  return `${Math.round(tokens / 1000)}k`;
}

export function AddModelsStep({ models, selected, onChange, emptyNote }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [type, setType] = useState<Modality | "all">("all");
  const [all, setAll] = useState(false);
  const needle = query.trim().toLowerCase();
  const rows = models.filter(
    (m) =>
      (type === "all" || (m.modality ?? "text") === type) &&
      (!needle || m.id.toLowerCase().includes(needle)),
  );
  const shown = all ? rows : rows.slice(0, PAGE);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  if (models.length === 0) return <p className="text-sm text-text-muted">{emptyNote}</p>;

  return (
    <div className="flex flex-col gap-3">
      <ModelsToolbar
        query={query}
        onQuery={setQuery}
        types={MODALITIES.filter((m) => models.some((x) => (x.modality ?? "text") === m))}
        type={type}
        onType={setType}
        searchClass="w-60"
        trailing={t("providers.add.models.selected", { n: selected.size, count: models.length })}
      />
      <div className="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border-subtle">
        {shown.map((m) => (
          <label
            key={m.id}
            className="flex min-h-9 cursor-pointer items-center gap-3 px-3 py-1.5 hover:bg-surface-hover"
          >
            <Checkbox
              checked={selected.has(m.id)}
              onChange={() => toggle(m.id)}
              aria-label={m.id}
            />
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">{m.id}</span>
            {m.tools === false ? (
              <span className="text-2xs text-text-muted">{t("providers.add.models.noTools")}</span>
            ) : null}
            <span className="w-12 text-right text-xs text-text-muted">
              {m.context_window ? windowLabel(m.context_window) : "—"}
            </span>
            <span className="w-24 text-xs text-text-muted">
              {t(`providers.modalities.${m.modality ?? "text"}`).split(" / ")[0]}
            </span>
          </label>
        ))}
        {rows.length > PAGE ? (
          <div className="flex items-center gap-2 px-3 py-2.5 text-xs text-text-muted">
            {t("providers.models.showing", { shown: shown.length, total: rows.length })}
            {all ? null : (
              <button
                type="button"
                className="font-label text-accent-text outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus-ring"
                onClick={() => setAll(true)}
              >
                {t("providers.models.showMore", { count: rows.length - PAGE })}
              </button>
            )}
          </div>
        ) : null}
      </div>
      <p className="text-xs text-text-muted">{t("providers.add.models.hint")}</p>
    </div>
  );
}
