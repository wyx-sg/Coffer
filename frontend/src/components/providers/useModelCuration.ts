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
// A failed or empty probe leaves the stored selection exactly as it was. A row
// switched on keeps the window the endpoint reported for it, so the projection
// can tell the agent (spec provider-switching "Resolve each provider model's
// context window").
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

  /** A row as a new curated entry: its kind and the window the endpoint reported. */
  const entry = (row: ProviderModel): ProviderModel => ({
    id: row.id,
    modality: modalityOf(row),
    ...(row.context_window ? { context_window: row.context_window } : {}),
  });

  /** The explicit list equivalent to what is on screen right now. */
  const materialised = (): ProviderModel[] => (unrestricted ? fetched.map(entry) : selected);

  const toggle = (row: ProviderModel) => {
    const base = materialised();
    write(
      base.some((m) => m.id === row.id)
        ? base.filter((m) => m.id !== row.id)
        : [...base, entry(row)],
    );
  };

  /** Switch every given row on or off in ONE write, from the same base a toggle uses. */
  const setMany = (picked: readonly ProviderModel[], on: boolean) => {
    const base = materialised();
    const ids = new Set(picked.map((m) => m.id));
    write(
      on
        ? [...base, ...picked.filter((m) => !base.some((b) => b.id === m.id)).map(entry)]
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
        : [...base, { ...entry(row), price }],
    );
  };

  /** Record the window the user set on a model ("You set"), or `null` to reset
   *  it — written out the way a price is. */
  const setWindow = (row: ProviderModel, tokens: number | null) => {
    const base = materialised();
    write(
      base.some((m) => m.id === row.id)
        ? base.map((m) => (m.id === row.id ? { ...m, user_context_window: tokens } : m))
        : [...base, { ...entry(row), user_context_window: tokens }],
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
    setWindow,
    pending: update.isPending,
    unrestricted,
  };
}
