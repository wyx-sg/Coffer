// src/components/providers/ProbeResult.tsx — the verdict of a dialog's Test: connected (with the time and count) or why not.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert, CircleCheck, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { EndpointTestResult } from "./useEndpointTest";

interface Props {
  result: EndpointTestResult | null;
  pending: boolean;
  /** The sentence under "Connected …" — each dialog says what happens next. */
  okNote: (count: number) => ReactNode;
  /** The sentence under a rejection or failure. */
  failNote: ReactNode;
}

export function ProbeResult({ result, pending, okNote, failNote }: Props) {
  const { t } = useTranslation();
  if (pending) {
    return (
      <p role="status" className="flex items-center gap-1.5 text-xs text-text-muted">
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
        {t("providers.test.running")}
      </p>
    );
  }
  if (!result) return null;
  const ok = result.kind === "ok";
  const refused = result.kind === "refused";
  const title = ok
    ? t("providers.test.connected", { ms: result.ms })
    : result.kind === "rejected"
      ? t("providers.test.rejected", { status: result.status ?? t("providers.test.noStatus") })
      : refused
        ? t("providers.test.refused")
        : t("providers.test.failed");
  return (
    <div
      role={ok ? "status" : "alert"}
      className={cn(
        "flex items-start gap-2.5 rounded-lg px-3 py-2.5",
        ok ? "bg-success-soft" : "bg-danger-soft",
      )}
    >
      {ok ? (
        <CircleCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
      ) : (
        <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      )}
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{title}</span>
        <span className="text-xs text-text-muted">
          {/* A refusal sent nothing, so the dialog's "check the key / endpoint" note does not apply. */}
          {ok ? okNote(result.models.length) : refused ? result.message : failNote}
          {result.kind === "failed" && result.message ? (
            <span className="mt-0.5 block break-words font-mono">{result.message}</span>
          ) : null}
        </span>
      </div>
    </div>
  );
}
