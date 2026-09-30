// src/components/providers/AddLocalRuntime.tsx — the Add dialog's local path: which runtime answers on this Mac.
//
// Detection is read-only (spec provider-switching "Detect a local model
// runtime without changing it"): with no URL it looks on each runtime's
// default port, with a loopback URL only there. It lists what answered — the
// runtime, its version, the wires it serves and its models — and the one
// picked is what the provider records. No key is asked for.
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { DetectLocalOut } from "@/lib/api/providers";
import { cn } from "@/lib/utils";
import { ProviderMark } from "./ProviderMark";

interface Props {
  detect: UseQueryResult<DetectLocalOut>;
  requested: boolean;
  chosen: number;
  onChoose: (index: number) => void;
  onDetect: () => void;
}

export function AddLocalRuntime({ detect, requested, chosen, onChoose, onDetect }: Props) {
  const { t } = useTranslation();
  const found = detect.data?.found ?? [];
  const busy = requested && detect.isFetching;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-label text-text">{t("providers.add.local.title")}</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="ml-auto"
          onClick={onDetect}
          disabled={busy}
        >
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Search aria-hidden />}
          {t("providers.add.local.detect")}
        </Button>
      </div>
      {busy ? (
        <p role="status" className="text-xs text-text-muted">
          {t("providers.add.local.looking")}
        </p>
      ) : detect.error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, detect.error)}
        </p>
      ) : requested && detect.data && found.length === 0 ? (
        <p className="text-xs text-text-muted">{t("providers.add.local.none")}</p>
      ) : found.length > 0 ? (
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
                "flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
                i === chosen
                  ? "border-accent bg-accent-soft"
                  : "border-border hover:bg-surface-hover",
              )}
            >
              <ProviderMark
                provider={{ base_url: f.base_url, protocol: "openai", local_runtime: f.runtime }}
                size="sm"
              />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-sm font-label text-text">
                  {t(`providers.runtimes.${f.runtime.runtime}`)}
                  {f.runtime.version ? ` ${f.runtime.version}` : ""}
                </span>
                <span className="truncate text-xs text-text-muted">
                  <span className="font-mono">{f.base_url}</span>
                  {" · "}
                  {f.runtime.wires?.length
                    ? t("providers.endpoint.wires", {
                        wires: f.runtime.wires.map((w) => t(`providers.wires.${w}`, w)).join(", "),
                      })
                    : t("providers.add.local.noWires")}
                  {" · "}
                  {t("providers.list.models", { count: f.models.length })}
                </span>
              </span>
            </button>
          ))}
        </div>
      ) : null}
      <p className="text-xs text-text-muted">{t("providers.add.local.keyless")}</p>
    </div>
  );
}
