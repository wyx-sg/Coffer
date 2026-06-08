// frontend/src/kinds/memory/MemoryMetricsHeader.tsx
//
// Memory store detail header: the store name and the fact-count / disk-bytes
// metrics line. Presentational — metrics are loaded by the page.
import { useTranslation } from "react-i18next";

import { formatBytes } from "@/lib/utils";
import { type MemoryStoreMetrics } from "./api";

interface Props {
  store: string;
  metrics: MemoryStoreMetrics | undefined;
}

export function MemoryMetricsHeader({ store, metrics }: Props) {
  const { t } = useTranslation();
  return (
    <header className="space-y-1">
      <h1 className="text-2xl font-semibold">{store}</h1>
      {metrics ? (
        <p className="text-sm text-muted-foreground">
          {t("memory.detail.metrics", {
            facts: metrics.fact_count,
            bytes: formatBytes(metrics.disk_bytes),
          })}
        </p>
      ) : null}
    </header>
  );
}
