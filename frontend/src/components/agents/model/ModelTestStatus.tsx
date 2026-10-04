// src/components/agents/model/ModelTestStatus.tsx — the connection-test line under Model in the Change model dialog.
//
// Testing… (spinner), Connection OK · latency (success), or the failure with a
// Retry (error). Review changes stays off until this line says OK.
import { CircleAlert, CircleCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { SwitchTestStatus } from "@/lib/hooks/useModelSwitchTest";

const K = "agents.changeModel.test";

export function ModelTestStatus({
  status,
  onRetry,
}: {
  status: SwitchTestStatus;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  if (status.state === "none") return null;
  if (status.state === "testing")
    return (
      <p role="status" className="inline-flex items-center gap-1.5 text-xs text-text-muted">
        <Spinner />
        {t(`${K}.testing`)}
      </p>
    );
  if (status.state === "passed")
    return (
      <p role="status" className="inline-flex items-center gap-1.5 text-xs text-success">
        <CircleCheck className="size-3.5 shrink-0" aria-hidden />
        {t(`${K}.ok`, { ms: status.ms })}
      </p>
    );
  return (
    <div role="alert" className="flex items-start gap-1.5 text-xs text-danger">
      <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 grow break-words">
        {t(`${K}.failed`, { message: status.message })}
      </span>
      <Button variant="outline" size="sm" className="shrink-0" onClick={onRetry}>
        {t(`${K}.retry`)}
      </Button>
    </div>
  );
}
