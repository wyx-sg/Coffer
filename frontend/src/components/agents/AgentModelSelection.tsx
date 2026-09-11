// frontend/src/components/agents/AgentModelSelection.tsx — the agent's own model
// catalogue, with a tick beside each model the user says they can actually run.
//
// WHY a person has to tick these. The catalogue is read out of the installed
// CLI and is cumulative: it names every model that release has heard of,
// including ones this ACCOUNT is not entitled to run. Which ones those are is a
// server-side fact with no local copy, and no field of the catalogue separates
// them — two models on the same price tier, with the same capabilities and the
// same knowledge cutoff, differ only in whether the account may use them. So
// Coffer shows the whole list and the user is the authority over it. A list
// hardcoded in Coffer would be wrong within a month and would give no clue why
// a newly released model never appeared.
//
// Nothing ticked means NOT CURATED: every model is offered, exactly as before
// this screen existed. It never means "no models" — Coffer has to work for
// someone who never opens this page.
//
// The draft is local until «保存»: ticking eleven boxes should be one write, not
// eleven, and an accidental tick should be undoable by navigating away.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import {
  useAgentModels,
  useAgentModelSelection,
  useSetAgentModelSelection,
} from "@/lib/hooks/useAgentModels";

export function AgentModelSelection({ agentType }: { agentType: string }) {
  const { t } = useTranslation();
  const catalogue = useAgentModels(agentType);
  const selection = useAgentModelSelection(agentType);
  const save = useSetAgentModelSelection(agentType);

  const models = useMemo(() => catalogue.data ?? [], [catalogue.data]);
  const applied = useMemo(() => selection.data ?? [], [selection.data]);

  // The draft re-syncs whenever the applied set changes (first load, after a
  // save, an external change). The dependency is the SERIALISED set, not the
  // array: a refetch returning the same ids is a new array and would otherwise
  // wipe an in-progress draft on every poll. Serialised rather than joined so
  // an id containing the separator cannot split into two.
  const [draft, setDraft] = useState<string[]>(applied);
  const appliedKey = JSON.stringify(applied);
  useEffect(() => {
    setDraft(JSON.parse(appliedKey) as string[]);
  }, [appliedKey]);

  const toggle = (id: string) =>
    setDraft((d) => (d.includes(id) ? d.filter((m) => m !== id) : [...d, id]));

  const dirty = JSON.stringify(draft) !== appliedKey;

  if (catalogue.isLoading || selection.isLoading) {
    return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>;
  }
  if (catalogue.isError || selection.isError) {
    return (
      <div className="flex items-start gap-3 text-sm text-destructive" role="alert">
        <AlertCircle className="mt-0.5 size-5 shrink-0" />
        <span>{translateApiError(t, catalogue.error ?? selection.error)}</span>
      </div>
    );
  }
  if (models.length === 0) {
    return (
      <div className="space-y-1.5">
        <Label>{t("agents.connection.builtinModelsTitle")}</Label>
        <p className="text-sm text-muted-foreground">{t("agents.connection.builtinModelsEmpty")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <Label>{t("agents.connection.builtinModelsTitle")}</Label>
      <p className="text-xs text-muted-foreground">{t("agents.models.curateHint")}</p>
      <ul className="space-y-1">
        {models.map((m) => (
          <li key={m.id}>
            <label className="flex cursor-pointer items-baseline gap-2 text-sm">
              <Checkbox
                checked={draft.includes(m.id)}
                onChange={() => toggle(m.id)}
                disabled={save.isPending}
                aria-label={m.id}
              />
              <span className="font-mono text-xs">{m.id}</span>
              {m.label && m.label !== m.id && (
                <span className="text-muted-foreground">{m.label}</span>
              )}
              {m.description && (
                <span className="text-xs text-muted-foreground">{m.description}</span>
              )}
            </label>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        {draft.length === 0
          ? t("agents.models.noneChosen", { total: models.length })
          : t("agents.models.chosenCount", { chosen: draft.length, total: models.length })}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          size="sm"
          onClick={() => save.mutate(draft)}
          disabled={!dirty || save.isPending}
        >
          {save.isPending && <Loader2 className="mr-1 size-3.5 animate-spin" />}
          {save.isPending ? t("common.saving") : t("common.save")}
        </Button>
        {save.isError && (
          <span role="alert" className="text-xs text-destructive">
            {t("agents.models.saveFailed")} {translateApiError(t, save.error)}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t("agents.connection.builtinModelsHint")}</p>
    </div>
  );
}
