// frontend/src/components/agents/AgentInstructionsTab.tsx — spec 004 item 1.
// The instructions hub on the agent detail page: edit the single master document
// and, for this agent, see delivery status and deliver / remove / adopt it. The
// master fans out into each agent's instructions file as a Coffer-managed block.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import {
  useAdoptInstructions,
  useAgentInstructionsStatus,
  useDeliverInstructions,
  useMasterInstructions,
  useSetMasterInstructions,
} from "@/lib/hooks/useAgentInstructions";

export function AgentInstructionsTab({ name }: { name: string }) {
  const { t } = useTranslation();
  const master = useMasterInstructions();
  const statusQ = useAgentInstructionsStatus(name);
  const setMaster = useSetMasterInstructions();
  const deliver = useDeliverInstructions(name);
  const adopt = useAdoptInstructions(name);

  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Sync the editor when the master (re)loads, keying on the fingerprint so a
  // server-side change is picked up without clobbering an in-progress edit on
  // every render.
  const fingerprint = master.data?.fingerprint;
  useEffect(() => {
    if (master.data) setDraft(master.data.content);
  }, [fingerprint, master.data]);

  // A type without an instructions file (e.g. openclaw) → 422 on status.
  const unsupported = statusQ.isError;

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(translateApiError(t, err));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-medium">{t("agents.instructions.title")}</h3>
        <p className="text-sm text-muted-foreground">{t("agents.instructions.description")}</p>
      </div>

      <Card>
        <CardContent className="space-y-3 py-4">
          <label className="block text-sm font-medium" htmlFor="master-instructions">
            {t("agents.instructions.masterLabel")}
          </label>
          <textarea
            id="master-instructions"
            className="block h-48 w-full rounded border bg-background px-2 py-1 font-mono text-xs"
            value={draft}
            placeholder={t("agents.instructions.masterPlaceholder")}
            onChange={(e) => setDraft(e.target.value)}
            disabled={master.isLoading}
          />
          <Button
            onClick={() =>
              run(() =>
                setMaster.mutateAsync({
                  content: draft,
                  expected_fingerprint: master.data?.fingerprint,
                }),
              )
            }
            disabled={setMaster.isPending || master.isLoading}
          >
            {setMaster.isPending ? t("common.saving") : t("agents.instructions.saveMaster")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 py-4">
          <div className="text-sm font-medium">{t("agents.instructions.deliveryHeading")}</div>
          {unsupported ? (
            <p className="text-sm text-muted-foreground">{t("agents.instructions.unsupported")}</p>
          ) : (
            <>
              <p className="text-sm" data-testid="instructions-status">
                {!statusQ.data?.delivered
                  ? t("agents.instructions.statusNotDelivered")
                  : statusQ.data.in_sync
                    ? t("agents.instructions.statusInSync")
                    : t("agents.instructions.statusDrifted")}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() => run(() => deliver.mutateAsync(true))}
                  disabled={deliver.isPending}
                >
                  {t("agents.instructions.deliver")}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => run(() => deliver.mutateAsync(false))}
                  disabled={deliver.isPending || !statusQ.data?.delivered}
                >
                  {t("agents.instructions.remove")}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => run(() => adopt.mutateAsync())}
                  disabled={adopt.isPending}
                >
                  {t("agents.instructions.adopt")}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{t("agents.instructions.adoptHelp")}</p>
            </>
          )}
        </CardContent>
      </Card>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
