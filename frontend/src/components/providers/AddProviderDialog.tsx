// src/components/providers/AddProviderDialog.tsx — Add model provider, in two steps: 1 Endpoint, 2 Models.
//
// Test lists the endpoint's models with the typed key inline — nothing is
// saved until Add (spec provider-switching "Introspect an unsaved connection
// with an inline secret"). The local path detects a runtime instead and sends
// what detection recorded (`local_runtime`) with its tool-capable models and
// their windows, and no key. Add is `POST /providers` with the chosen
// `models` (none chosen = every model offered). Failures render inline.
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Plug } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { useCreateProvider, useDetectLocalRuntimes } from "@/lib/hooks/useProviders";
import { presetById, type PresetId } from "@/lib/providers/presets";
import { AddEndpointStep } from "./AddEndpointStep";
import { AddLocalRuntime } from "./AddLocalRuntime";
import { AddModelsStep, type CandidateModel } from "./AddModelsStep";
import { createBody, localCandidates, localProtocolsOf } from "./addProviderPlan";
import { ProbeResult } from "./ProbeResult";
import { endpointSchema, type EndpointValues } from "./providerSchemas";
import { StepMarker } from "./StepMarker";
import { useEndpointTest } from "./useEndpointTest";

interface Props {
  /** The preset to open on; `null` = closed. */
  preset: PresetId | null;
  onClose: () => void;
  onCreated: (provider: Provider) => void;
}

function seed(id: PresetId): EndpointValues {
  const p = presetById(id);
  return {
    local: !!p.local,
    name: "",
    protocol: p.protocol || "openai",
    baseUrl: p.local ? "" : p.baseUrl,
    secret: "",
  };
}

export function AddProviderDialog({ preset, onClose, onCreated }: Props) {
  const { t } = useTranslation();
  const create = useCreateProvider();
  const test = useEndpointTest(t);
  const [presetId, setPresetId] = useState<PresetId>("anthropic");
  const [step, setStep] = useState<1 | 2>(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detectUrl, setDetectUrl] = useState<string | null | undefined>(undefined);
  const [chosen, setChosen] = useState(0);
  const form = useForm<EndpointValues>({
    resolver: zodResolver(endpointSchema(t)),
    defaultValues: seed("anthropic"),
  });
  const local = form.watch("local");
  const detect = useDetectLocalRuntimes(
    detectUrl ?? null,
    preset !== null && local && detectUrl !== undefined,
  );
  const found = detect.data?.found ?? [];
  const runtime = found[chosen] ?? null;
  const localProtocols = localProtocolsOf(runtime);

  const pickPreset = (id: PresetId) => {
    const name = form.getValues("name");
    setPresetId(id);
    form.reset({ ...seed(id), name });
    test.reset();
    setChosen(0);
    setDetectUrl(presetById(id).local ? null : undefined);
  };

  useEffect(() => {
    if (preset === null) return;
    setPresetId(preset);
    form.reset(seed(preset));
    setStep(1);
    setSelected(new Set());
    setChosen(0);
    setDetectUrl(presetById(preset).local ? null : undefined);
    test.reset();
    create.reset();
    // Re-seed only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset]);

  // A detected runtime that does not serve the chosen wire moves to one it does.
  const protocol = form.watch("protocol");
  useEffect(() => {
    if (local && localProtocols.length > 0 && !localProtocols.includes(protocol)) {
      form.setValue("protocol", localProtocols[0]);
    }
  });

  const probe = (v: EndpointValues) => ({
    provider: v.protocol,
    base_url: v.baseUrl.trim(),
    secret_value: v.protocol === "ollama" ? null : v.secret,
  });

  const candidates: CandidateModel[] = local
    ? localCandidates(runtime)
    : test.result?.kind === "ok"
      ? test.result.models
      : [];

  const next = form.handleSubmit(async (v) => {
    if (local) {
      setSelected(new Set(candidates.filter((m) => m.tools !== false).map((m) => m.id)));
    } else if (!test.result) {
      await test.run(probe(v));
    }
    setStep(2);
  });

  const add = async () => {
    const body = createBody(form.getValues(), runtime, candidates, selected);
    try {
      const created = await create.mutateAsync(body);
      onCreated(created);
      onClose();
    } catch {
      // rendered inline below
    }
  };

  const testResult = (
    <ProbeResult
      result={test.result}
      pending={test.isPending}
      okNote={(count) => t("providers.test.addOk", { count })}
      failNote={t("providers.test.addFail")}
    />
  );

  return (
    <Dialog open={preset !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        aria-describedby={undefined}
        className="max-h-[90vh] max-w-[640px] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>{t("providers.add.title")}</DialogTitle>
        </DialogHeader>
        <StepMarker step={step} />
        {step === 1 ? (
          <AddEndpointStep
            form={form}
            presetId={presetId}
            onPreset={pickPreset}
            localProtocols={localProtocols}
            onEdited={test.reset}
            result={local ? null : testResult}
            localPanel={
              <AddLocalRuntime
                detect={detect}
                requested={detectUrl !== undefined}
                chosen={chosen}
                onChoose={setChosen}
                onDetect={() => {
                  const url = form.getValues("baseUrl").trim() || null;
                  if (url === detectUrl) void detect.refetch();
                  else setDetectUrl(url);
                }}
              />
            }
          />
        ) : (
          <AddModelsStep
            models={candidates}
            selected={selected}
            onChange={setSelected}
            emptyNote={t("providers.add.models.empty")}
          />
        )}
        {create.error != null ? (
          <p role="alert" className="text-sm text-danger">
            {translateApiError(t, create.error)}
          </p>
        ) : null}
        <DialogFooter>
          {step === 1 ? (
            <>
              {local ? null : (
                <Button
                  type="button"
                  variant="outline"
                  className="sm:mr-auto"
                  disabled={test.isPending}
                  onClick={() => void form.handleSubmit((v) => test.run(probe(v)))()}
                >
                  <Plug aria-hidden />{" "}
                  {test.result ? t("providers.test.again") : t("providers.actions.test")}
                </Button>
              )}
              <Button type="button" variant="ghost" onClick={onClose}>
                {t("common.cancel")}
              </Button>
              <Button type="button" onClick={() => void next()} disabled={test.isPending}>
                {t("providers.add.next")}
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                variant="outline"
                className="sm:mr-auto"
                onClick={() => setStep(1)}
              >
                {t("providers.add.back")}
              </Button>
              <Button type="button" variant="ghost" onClick={onClose}>
                {t("common.cancel")}
              </Button>
              <Button type="button" onClick={() => void add()} disabled={create.isPending}>
                {t("providers.add.submit")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
