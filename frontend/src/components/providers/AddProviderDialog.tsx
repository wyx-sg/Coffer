// src/components/providers/AddProviderDialog.tsx — Add model provider, in two steps: 1 Endpoint, 2 Models.
//
// Test lists the endpoint's models with the typed key inline — nothing is
// saved until Add (spec provider-switching "Introspect an unsaved connection
// with an inline secret"). The local path detects a runtime instead and sends
// what detection recorded (`local_runtime`) with its tool-capable models and
// their windows, and no key. Add is `POST /providers` with the chosen
// `models` (none chosen = every model offered). Failures render inline.
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { useCreateProvider, useDetectLocalRuntimes } from "@/lib/hooks/useProviders";
import { presetById, type PresetId } from "@/lib/providers/presets";
import { AddProviderFooter } from "./AddProviderFooter";
import { AddEndpointStep } from "./AddEndpointStep";
import { AddLocalRuntime } from "./AddLocalRuntime";
import { AddModelsStep, type CandidateModel } from "./AddModelsStep";
import { createBody, keyOf, localCandidates, localProtocolsOf } from "./addProviderPlan";
import { labelNewKey } from "./labelNewKey";
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
    secret: null,
  };
}

export function AddProviderDialog({ preset, onClose, onCreated }: Props) {
  const { t } = useTranslation();
  const create = useCreateProvider();
  const qc = useQueryClient();
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
  const vendorRuntime = presetById(presetId).runtime;
  // Name once a runtime is chosen (or an address typed); the address only when nothing answered.
  const showName = local && runtime !== null;
  const showUrl = local && !detect.isFetching && detect.data !== undefined && found.length === 0;
  const nothingToAdd = local && runtime === null;

  // Start on the runtime the vendor stands for, else the first that answered.
  useEffect(() => {
    const at = found.findIndex((f) => f.runtime.runtime === vendorRuntime);
    setChosen(at >= 0 ? at : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detect.data, vendorRuntime]);

  // The name follows the chosen runtime until the person types their own.
  const autoName = useRef("");
  useEffect(() => {
    if (!runtime) return;
    const next = t("providers.add.local.defaultName", {
      runtime: t(`providers.runtimes.${runtime.runtime.runtime}`),
    });
    const current = form.getValues("name");
    if (current === "" || current === autoName.current) {
      form.setValue("name", next);
      autoName.current = next;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runtime?.runtime.runtime, runtime?.base_url]);

  const detectAgain = () => {
    const url = form.getValues("baseUrl").trim() || null;
    if (url === detectUrl) void detect.refetch();
    else setDetectUrl(url);
  };

  const pickPreset = (id: PresetId) => {
    const name = form.getValues("name");
    setPresetId(id);
    // A name the person did not type follows the vendor, not the last one.
    form.reset({ ...seed(id), name: name === autoName.current ? "" : name });
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

  // The chosen runtime sets the wire: the first an agent can use.
  const protocol = form.watch("protocol");
  const runtimeKey = runtime ? `${runtime.runtime.runtime}@${runtime.base_url}` : "";
  useEffect(() => {
    if (local && localProtocols.length > 0) form.setValue("protocol", localProtocols[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runtimeKey, local]);
  useEffect(() => {
    if (local && localProtocols.length > 0 && !localProtocols.includes(protocol)) {
      form.setValue("protocol", localProtocols[0]);
    }
  });

  const probe = (v: EndpointValues) => ({
    provider: v.protocol,
    base_url: v.baseUrl.trim(),
    ...keyOf(v.secret),
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
      await labelNewKey(qc, form.getValues("secret"), created.secret_ref);
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
            showName={showName}
            showUrl={showUrl}
            onEdited={test.reset}
            result={local ? null : testResult}
            localPanel={
              <AddLocalRuntime
                detect={detect}
                requested={detectUrl !== undefined}
                chosen={chosen}
                onChoose={setChosen}
                vendorRuntime={vendorRuntime}
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
        <AddProviderFooter
          step={step}
          local={local}
          detecting={detect.isFetching}
          testing={test.isPending}
          tested={test.result !== null}
          nothingToAdd={nothingToAdd}
          adding={create.isPending}
          onDetect={detectAgain}
          onTest={() => void form.handleSubmit((v) => test.run(probe(v)))()}
          onNext={() => void next()}
          onBack={() => setStep(1)}
          onAdd={() => void add()}
          onClose={onClose}
        />
      </DialogContent>
    </Dialog>
  );
}
