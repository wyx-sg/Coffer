// frontend/src/components/RawLog.tsx
import { useTranslation } from "react-i18next";

interface Props {
  /** The full underlying record for one log row, rendered verbatim. */
  record: unknown;
}

/**
 * The raw log view shared by the audit log and the MCP invocation log: it
 * pretty-prints the row's full underlying JSON record in a monospace,
 * horizontally-scrollable block. Both logs expand a row to this same view.
 */
export function RawLog({ record }: Props) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5 text-xs">
      <div className="font-medium text-muted-foreground">{t("common.rawLog")}</div>
      <pre className="max-h-96 overflow-auto rounded-md bg-secondary/50 p-3 font-mono text-xs leading-relaxed text-foreground/80">
        {JSON.stringify(record, null, 2)}
      </pre>
    </div>
  );
}
