// src/components/providers/ModelEditDialogs.tsx — the price and context-window dialogs a Models row opens.
import type { ModelPrice, ModelWindow, ProviderModel } from "@/lib/api/providers";
import { SetPriceDialog } from "./SetPriceDialog";
import { SetWindowDialog } from "./SetWindowDialog";
import type { useModelCuration } from "./useModelCuration";

interface Props {
  cur: ReturnType<typeof useModelCuration>;
  /** The model whose price is being edited, or `null`. */
  pricing: string | null;
  /** The model whose window is being edited, or `null`. */
  sizing: string | null;
  price: ModelPrice | undefined;
  window: ModelWindow | undefined;
  onClose: () => void;
}

export function ModelEditDialogs({ cur, pricing, sizing, price, window, onClose }: Props) {
  const withRow = (id: string | null, act: (row: ProviderModel) => void) => {
    const row = id ? cur.rows.find((m) => m.id === id) : undefined;
    if (row) act(row);
  };
  return (
    <>
      <SetPriceDialog
        model={pricing}
        current={price}
        onClose={onClose}
        onSave={(p) => withRow(pricing, (row) => cur.setPrice(row, p))}
        onReset={() => withRow(pricing, (row) => cur.setPrice(row, null))}
      />
      <SetWindowDialog
        model={sizing}
        current={window}
        onClose={onClose}
        onSave={(tokens) => withRow(sizing, (row) => cur.setWindow(row, tokens))}
        onReset={() => withRow(sizing, (row) => cur.setWindow(row, null))}
      />
    </>
  );
}
