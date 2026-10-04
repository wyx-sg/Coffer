// src/components/providers/AddLocalRuntime.tsx — the Add dialog's local path: "Found on this Mac".
//
// Detection is read-only (spec provider-switching "Detect a local model
// runtime without changing it"): with no URL it looks on each runtime's
// default port, with a loopback URL only there. It lists what answered — the
// runtime, its version, the wires it serves and its models — and the one
// picked is what the provider records. The runtime the chosen vendor stands
// for, when nothing answers for it, is listed as not running and cannot be
// picked. With nothing found at all, setting a runtime up is handed to the
// person's agent (the detect response carries the prompt) and typing a running
// runtime's address stays. "Detect again" is the dialog footer's one button.
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { translateApiError } from "@/lib/api/errors";
import type { DetectLocalOut } from "@/lib/api/providers";
import { cn } from "@/lib/utils";
import { ProblemBox } from "./ProblemBox";

const DEFAULT_PORT = { ollama: 11434, lmstudio: 1234 } as const;

interface Props {
  detect: UseQueryResult<DetectLocalOut>;
  requested: boolean;
  chosen: number;
  onChoose: (index: number) => void;
  /** The runtime the picked vendor stands for; listed as "Not running" when it did not answer. */
  vendorRuntime?: "ollama" | "lmstudio";
}

export function AddLocalRuntime({ detect, requested, chosen, onChoose, vendorRuntime }: Props) {
  const { t, i18n } = useTranslation();
  const found = detect.data?.found ?? [];
  const busy = requested && detect.isFetching;
  const handoff = detect.data?.handoff?.prompt;
  const missing =
    vendorRuntime && !found.some((f) => f.runtime.runtime === vendorRuntime) ? vendorRuntime : null;
  const ask = handoff ? <AgentHandoff size="sm" prompt={handoff} /> : null;

  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-label text-text">{t("providers.add.local.title")}</span>
      {busy ? (
        <p role="status" className="flex items-center gap-1.5 text-xs text-text-muted">
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
          {t("providers.add.local.looking")}
        </p>
      ) : detect.error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, detect.error)}
        </p>
      ) : requested && detect.data && found.length === 0 ? (
        <ProblemBox
          tone="neutral"
          title={t("providers.add.local.noneTitle")}
          body={t("providers.add.local.none")}
        >
          {ask}
        </ProblemBox>
      ) : (
        <div
          role="radiogroup"
          aria-label={t("providers.add.local.title")}
          className="flex flex-col gap-1.5"
        >
          {found.map((f, i) => (
            <button
              key={`${f.runtime.runtime}-${f.base_url}`}
              type="button"
              role="radio"
              aria-checked={i === chosen}
              onClick={() => onChoose(i)}
              className={cn(
                "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
                i === chosen
                  ? "border-accent bg-accent-soft"
                  : "border-border hover:bg-surface-hover",
              )}
            >
              <Radio on={i === chosen} />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="flex items-center gap-2">
                  <span className="flex-1 text-sm font-label text-text">
                    {t(`providers.runtimes.${f.runtime.runtime}`)}
                    {f.runtime.version ? ` ${f.runtime.version}` : ""}
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-xs text-success">
                    <span aria-hidden className="size-1.5 rounded-full bg-success" />
                    {t("providers.add.local.running")}
                  </span>
                </span>
                <span className="truncate text-xs text-text-muted">
                  <span className="font-mono">{f.base_url.replace(/^https?:\/\//, "")}</span>
                  {" · "}
                  {f.runtime.wires?.length
                    ? t("providers.endpoint.wires", {
                        wires: new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(
                          f.runtime.wires.map((w) => t(`providers.wires.${w}`, w)),
                        ),
                      })
                    : t("providers.add.local.noWires")}
                  {" · "}
                  {t("providers.list.models", { count: f.models.length })}
                </span>
              </span>
            </button>
          ))}
          {missing ? (
            <div
              aria-disabled
              className="flex items-start gap-2.5 rounded-lg border border-border-subtle px-3 py-2.5"
            >
              <Radio on={false} />
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="flex items-center gap-2">
                  <span className="flex-1 text-sm font-label text-text">
                    {t(`providers.runtimes.${missing}`)}
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-xs text-warning">
                    <span aria-hidden className="size-1.5 rounded-full bg-warning" />
                    {t("providers.add.local.notRunning")}
                  </span>
                </span>
                <span className="text-xs text-text-muted">
                  {t("providers.add.local.notRunningBody", { port: DEFAULT_PORT[missing] })}
                </span>
                {ask ? <span className="mt-1 flex items-center gap-2">{ask}</span> : null}
              </span>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Radio({ on }: { on: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "mt-0.5 inline-flex size-3.5 shrink-0 items-center justify-center rounded-full border",
        on ? "border-accent" : "border-border",
      )}
    >
      {on ? <span className="size-2 rounded-full bg-accent" /> : null}
    </span>
  );
}
