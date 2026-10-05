// src/components/providers/useModelCuration.ts — which of the endpoint's models a provider offers, and what kind each is.
//
// EMPTY selection = NO RESTRICTION: every model the endpoint serves is offered,
// so every row reads as on until the user narrows it. Narrowing writes the
// explicit list "no restriction" stood for, minus the row, and never
// collapses back to empty when a later tick covers everything again — that
// would discard the types corrected on those rows. Switching a row or
// correcting an offered row's type PATCHes the whole set as `models`. A type
// picked on a row not offered yet is held here until its switch carries it in
// (spec provider-switching "Introspect the endpoint when the Models tab opens").
// Bulk on/off (`setMany`) computes the new set from the same base and saves once.
// A failed or empty probe leaves the stored selection exactly as it was.
import { useState } from "react";

import type { CuratedPrice, Modality, Provider, ProviderModel } from "@/lib/api/providers";
import { useUpdateProvider } from "@/lib/hooks/useProviders";

export function useModelCuration(provider: Provider, fetched: readonly ProviderModel[]) {
  const update = useUpdateProvider();
  const [held, setHeld] = useState<Record<string, Modality>>({});

  const selected = provider.models ?? [];
  const unrestricted = selected.length === 0;
  const isCurated = (id: string) => selected.some((m) => m.id === id);
  const isOn = (id: string) => unrestricted || isCurated(id);
  // What the endpoint offers, plus anything curated it no longer lists, so a
  // stale pick stays visible and can be switched off.
  const rows: ProviderModel[] = [...selected, ...fetched.filter((m) => !isCurated(m.id))];

  /** The STORED modality once curated, else a held correction, else the guess. */
  const modalityOf = (row: ProviderModel): Modality =>
    selected.find((m) => m.id === row.id)?.modality ?? held[row.id] ?? row.modality ?? "text";

  const write = (models: ProviderModel[]) =>
    update.mutate({ uid: provider.uid, patch: { models } });

  /** The explicit list equivalent to what is on screen right now. */
  const materialised = (): ProviderModel[] =>
    unrestricted ? fetched.map((m) => ({ id: m.id, modality: modalityOf(m) })) : selected;

  const toggle = (row: ProviderModel) => {
    const base = materialised();
    write(
      base.some((m) => m.id === row.id)
        ? base.filter((m) => m.id !== row.id)
        : [...base, { id: row.id, modality: modalityOf(row) }],
    );
  };

  /** Switch every given row on or off in ONE write, from the same base a toggle uses. */
  const setMany = (picked: readonly ProviderModel[], on: boolean) => {
    const base = materialised();
    const ids = new Set(picked.map((m) => m.id));
    write(
      on
        ? [
            ...base,
            ...picked
              .filter((m) => !base.some((b) => b.id === m.id))
              .map((m) => ({ id: m.id, modality: modalityOf(m) })),
          ]
        : base.filter((m) => !ids.has(m.id)),
    );
  };

  const setModality = (row: ProviderModel, modality: Modality) => {
    if (unrestricted) {
      write(materialised().map((m) => (m.id === row.id ? { ...m, modality } : m)));
    } else if (!isCurated(row.id)) {
      setHeld((h) => ({ ...h, [row.id]: modality }));
    } else {
      write(selected.map((m) => (m.id === row.id ? { ...m, modality } : m)));
    }
  };

  /** Record the user's own price on a model ("You set"), or `null` to reset
   *  it. An unrestricted provider is written out first, as a toggle does, so
   *  setting a price never narrows what it offers; a row not offered yet is
   *  switched on with it. */
  const setPrice = (row: ProviderModel, price: CuratedPrice | null) => {
    const base = materialised();
    write(
      base.some((m) => m.id === row.id)
        ? base.map((m) => (m.id === row.id ? { ...m, price } : m))
        : [...base, { id: row.id, modality: modalityOf(row), price }],
    );
  };

  return {
    rows,
    isOn,
    modalityOf,
    toggle,
    setMany,
    setModality,
    setPrice,
    pending: update.isPending,
    unrestricted,
  };
}
