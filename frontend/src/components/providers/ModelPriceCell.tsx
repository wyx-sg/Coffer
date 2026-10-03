// src/components/providers/ModelPriceCell.tsx — one model's price on a provider, marked only when it is not the provider's usual.
//
// "$1.25 · $10.00 / 1M" (input · output per 1M tokens); clicking it opens the
// price dialog. Where prices come from is said once, in the Models line under
// the title (`providerPriceSource`), so a row carries a tag only when it is
// the exception: You set (your own price), or a source other than the
// provider's usual. A model nothing prices reads "—" with Set price…; a local
// runtime reads "Local · no cost" (spec provider-switching "Resolve each
// model's price from the provider, its API, or the bundled list").
import { useTranslation } from "react-i18next";

import type { ModelPrice } from "@/lib/api/providers";

const TAG =
  "inline-flex h-[18px] items-center whitespace-nowrap rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted";
const LINK =
  "text-xs font-label text-accent-text outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus-ring";

/** "$1.25", or "—" for a rate nothing states. */
function formatRate(value: number | null | undefined, lang: string): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(lang, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: value > 0 && value < 0.01 ? 4 : 2,
  }).format(value);
}

interface Props {
  id: string;
  price: ModelPrice | undefined;
  /** The source most of this provider's prices come from; a row with another is tagged. */
  usual: ModelPrice["source"];
  /** Opens the price dialog; absent on a local runtime. */
  onEdit?: () => void;
  disabled?: boolean;
}

export function ModelPriceCell({ id, price, usual, onEdit, disabled }: Props) {
  const { t, i18n } = useTranslation();
  if (price?.source === "local") {
    return <span className="text-xs text-text-muted">{t("providers.prices.local")}</span>;
  }
  if (!price || price.source === null || price.source === undefined) {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-text-muted">
        <span aria-label={t("providers.prices.noneAria", { id })}>—</span>
        {onEdit ? (
          <button type="button" className={LINK} onClick={onEdit} disabled={disabled}>
            {t("providers.prices.set")}
          </button>
        ) : null}
      </span>
    );
  }
  const rates = t("providers.prices.rates", {
    input: formatRate(price.input, i18n.language),
    output: formatRate(price.output, i18n.language),
  });
  const tag =
    price.source === "user"
      ? t("providers.prices.source.user")
      : price.source === usual
        ? null
        : price.source === "provider"
          ? t("providers.prices.source.provider", { name: price.source_name ?? "" })
          : t("providers.prices.source.bundled");
  return (
    <span className="inline-flex items-center justify-end gap-1.5 whitespace-nowrap text-xs text-text">
      {onEdit ? (
        <button
          type="button"
          className="whitespace-nowrap font-mono text-xs outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus-ring"
          onClick={onEdit}
          disabled={disabled}
          title={price.tiered ? t("providers.prices.tiered") : undefined}
          aria-label={t("providers.prices.editAria", { id, rates })}
        >
          {rates}
        </button>
      ) : (
        <span className="whitespace-nowrap font-mono">{rates}</span>
      )}
      {tag ? <span className={TAG}>{tag}</span> : null}
    </span>
  );
}
