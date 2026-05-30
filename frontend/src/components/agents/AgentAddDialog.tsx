// frontend/src/components/agents/AgentAddDialog.tsx — spec 004-agent-registry.
// One combined "Add agent" dialog. On open it auto-runs candidate detection
// (discovery + confirm: nothing is registered silently) and lists installed-
// but-unregistered agents as a checklist, default all ticked. Below that, an
// "Add manually" disclosure (AgentManualAddForm) reveals the manual form. Both
// paths register via useRegisterAgent; after a successful add the dialog shows
// the result list and offers Done.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { AgentManualAddForm } from "@/components/agents/AgentManualAddForm";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import { useAgentCandidates, useRegisterAgent } from "@/lib/hooks/useAgents";

export function AgentAddDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const candidates = useAgentCandidates(open);
  const register = useRegisterAgent();

  // Which candidate types are ticked (default: all). Keyed by agent type.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Once the user confirms an add (either path), we switch to a result view.
  const [added, setAdded] = useState<string[] | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Synchronous re-entry guard: register.isPending only flips after the first
  // mutateAsync resolves a render, so a fast double-click could otherwise start
  // the registration loop twice (duplicate POSTs / spurious 409). A ref updates
  // immediately, before any re-render.
  const submittingRef = useRef(false);

  const list = candidates.data ?? [];

  // Default-select every candidate as it loads.
  useEffect(() => {
    if (candidates.data) {
      setSelected(new Set(candidates.data.map((c) => c.type)));
    }
  }, [candidates.data]);

  // Reset transient state whenever the dialog closes.
  useEffect(() => {
    if (!open) {
      setAdded(null);
      setErrorMsg(null);
    }
  }, [open]);

  const toggle = (type: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });

  const addSelected = async () => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setErrorMsg(null);
    const chosen = list.filter((c) => selected.has(c.type));
    const ok: string[] = [];
    try {
      // Register each chosen candidate under its suggested per-type name.
      for (const c of chosen) {
        await register.mutateAsync({ type: c.type, name: c.suggested_name });
        ok.push(c.suggested_name);
      }
      setAdded(ok);
    } catch (e) {
      setAdded(ok); // keep the ones that succeeded before the failure
      setErrorMsg(translateApiError(t, e));
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
      onCreated(); // refresh the agents list (and the candidate set) either way
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("agents.addTitle")}</DialogTitle>
          <DialogDescription>{t("agents.addSubtitle")}</DialogDescription>
        </DialogHeader>

        {added ? (
          <div className="space-y-3 py-2">
            {added.length > 0 ? (
              <>
                <div className="flex items-center gap-2 text-sm font-medium">
                  <CheckCircle2 className="size-5 text-primary" />
                  {t("agents.detectDialog.complete")}
                </div>
                <ul className="space-y-1">
                  {added.map((n) => (
                    <li
                      key={n}
                      className="rounded-md border bg-card/60 px-3 py-2 text-sm font-medium"
                    >
                      {n}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            {errorMsg ? (
              <div className="flex items-start gap-3 text-sm text-destructive" role="alert">
                <AlertCircle className="mt-0.5 size-5 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="space-y-4">
            {/* Detected agents section. */}
            <section className="space-y-2">
              <h3 className="text-sm font-medium">{t("agents.detectedHeading")}</h3>
              {candidates.isPending ? (
                <div className="flex items-center gap-3 py-4 text-sm text-muted-foreground">
                  <Loader2 className="size-5 animate-spin" />
                  {t("agents.detectDialog.scanning")}
                </div>
              ) : candidates.isError ? (
                <div className="flex items-start gap-3 py-2 text-sm text-destructive" role="alert">
                  <AlertCircle className="mt-0.5 size-5 shrink-0" />
                  <span>{translateApiError(t, candidates.error)}</span>
                </div>
              ) : list.length === 0 ? (
                <p className="py-2 text-sm text-muted-foreground">
                  {t("agents.detectDialog.empty")}
                </p>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">{t("agents.detectDialog.found")}</p>
                  <ul className="space-y-1">
                    {list.map((c) => (
                      <li key={c.type}>
                        <label className="flex cursor-pointer items-center gap-3 rounded-md border bg-card/60 px-3 py-2 text-sm">
                          <input
                            type="checkbox"
                            checked={selected.has(c.type)}
                            onChange={() => toggle(c.type)}
                          />
                          <span className="flex-1">
                            <span className="font-medium">{c.display_name}</span>
                            <span className="block font-mono text-xs text-muted-foreground">
                              {c.config_dir}
                            </span>
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                  <Button
                    type="button"
                    onClick={addSelected}
                    disabled={submitting || register.isPending || selected.size === 0}
                  >
                    {submitting || register.isPending
                      ? t("common.saving")
                      : t("agents.detectDialog.addSelected", { n: selected.size })}
                  </Button>
                </div>
              )}
            </section>

            {/* Manual-add disclosure + form. */}
            <AgentManualAddForm
              onAdded={(name) => {
                setAdded([name]);
                onCreated();
              }}
            />
          </div>
        )}

        <DialogFooter>
          {added ? (
            <Button onClick={() => onOpenChange(false)}>{t("common.done")}</Button>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
