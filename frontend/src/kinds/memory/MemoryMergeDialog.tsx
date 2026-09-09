// frontend/src/kinds/memory/MemoryMergeDialog.tsx
// AI-assisted same-project store merge (spec 007 amendment 2026-07-10).
// Opening the dialog runs the merge scan (POST /memory_stores/merge_scan);
// each proposal shows the pair, the confidence + judged-by badge, and the
// engine's reason, with per-proposal swap-direction and Merge actions. A
// merge invalidates ["memory-stores"] so the list drops the retired store.
// `engine: "no_model"` renders the deterministic proposals plus a hint to
// configure the internal engine (Settings → LLM connections).
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, ArrowRight, GitMerge } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import {
  mergeMemoryStores,
  mergeScanMemoryStores,
  type MergeProposalOut,
  type StoreEvidenceOut,
} from "./api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Readable identity for one side of a proposal: label > root basename > name. */
function evidenceName(e: StoreEvidenceOut): string {
  if (e.label) return e.label;
  if (e.root) {
    const parts = e.root.replace(/[\\/]+$/, "").split(/[\\/]/);
    const base = parts[parts.length - 1];
    if (base) return base;
  }
  return e.store;
}

export function MemoryMergeDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [proposals, setProposals] = useState<MergeProposalOut[]>([]);
  // Per-proposal direction override, keyed by the PAIR identity (not the array
  // index — merging one proposal filters the list, and an index key would let
  // a stale swap silently attach to a different pair).
  const [swapped, setSwapped] = useState<Record<string, boolean>>({});
  const [mergingKey, setMergingKey] = useState<string | null>(null);

  const scan = useMutation({
    mutationFn: mergeScanMemoryStores,
    onSuccess: (data) => {
      setProposals(data.proposals);
      setSwapped({});
    },
  });

  // Re-scan each time the dialog opens (stores may have changed since).
  useEffect(() => {
    if (open) {
      setProposals([]);
      scan.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const merge = useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) =>
      mergeMemoryStores(source, target),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["memory-stores"] });
      // Drop every proposal touching either merged store — their evidence is stale.
      setProposals((prev) =>
        prev.filter(
          (p) =>
            ![p.source, p.target].some((s) => s === vars.source || s === vars.target),
        ),
      );
      setMergingKey(null);
    },
    onError: () => setMergingKey(null),
  });

  const scanning = scan.isPending;
  const noModel = scan.data?.engine === "no_model";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("memory.merge.title")}</DialogTitle>
          <DialogDescription>{t("memory.merge.description")}</DialogDescription>
        </DialogHeader>

        {scanning ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            {t("memory.merge.scanning")}
          </p>
        ) : scan.error ? (
          <p className="py-4 text-sm text-destructive">{translateApiError(t, scan.error)}</p>
        ) : (
          <div className="space-y-3">
            {noModel ? (
              <p className="rounded-md border border-border/60 bg-secondary px-3 py-2 text-xs text-muted-foreground">
                {t("memory.merge.noModelHint")}
              </p>
            ) : null}

            {proposals.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                {t("memory.merge.noCandidates")}
              </p>
            ) : (
              <ul className="max-h-96 space-y-3 overflow-y-auto pr-1">
                {proposals.map((p) => {
                  const pairKey = `${p.source}->${p.target}`;
                  const isSwapped = swapped[pairKey] ?? false;
                  const [src, dst] = isSwapped
                    ? [p.target_evidence, p.source_evidence]
                    : [p.source_evidence, p.target_evidence];
                  const pending = merge.isPending && mergingKey === pairKey;
                  return (
                    <li key={pairKey} className="rounded-md border border-border/60 p-3">
                      <div className="flex min-w-0 items-center gap-2 text-sm">
                        <span className="min-w-0 truncate font-medium">{evidenceName(src)}</span>
                        <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 truncate font-medium">{evidenceName(dst)}</span>
                        <span className="ml-auto inline-flex shrink-0 rounded-full border border-border/60 bg-secondary px-2 py-0.5 text-xs">
                          {t(`memory.merge.confidence.${p.confidence}`, p.confidence)}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {p.judged_by === "remote"
                          ? t("memory.merge.judgedByRemote")
                          : t("memory.merge.judgedByEngine")}
                        {" — "}
                        {p.reason}
                      </p>
                      <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
                        {src.store} ({t("memory.merge.factCount", { count: src.facts })}) →{" "}
                        {dst.store} ({t("memory.merge.factCount", { count: dst.facts })})
                      </p>
                      <div className="mt-2 flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={merge.isPending}
                          onClick={() => setSwapped((s) => ({ ...s, [pairKey]: !isSwapped }))}
                        >
                          <ArrowLeftRight className="mr-1 size-3.5" />
                          {t("memory.merge.swap")}
                        </Button>
                        <Button
                          size="sm"
                          disabled={merge.isPending}
                          onClick={() => {
                            setMergingKey(pairKey);
                            merge.mutate({ source: src.store, target: dst.store });
                          }}
                        >
                          <GitMerge className="mr-1 size-3.5" />
                          {pending ? t("memory.merge.merging") : t("memory.merge.merge")}
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            {merge.error ? (
              <p className="text-sm text-destructive">{translateApiError(t, merge.error)}</p>
            ) : null}
            {scan.data?.truncated ? (
              <p className="text-xs text-muted-foreground">{t("memory.merge.truncated")}</p>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
