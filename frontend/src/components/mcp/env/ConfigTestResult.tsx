// src/components/mcp/env/ConfigTestResult.tsx — the outcome of testing the
// edit dialog's unsaved config, shown above its footer (board Mcp-Edit):
// "Test failed after 3.0 s · <reason>" with the message and "Nothing was
// saved.", or "Test passed in 1.4 s · 26 tools, 0 resources, 0 prompts".
import { useTranslation } from "react-i18next";
import { CircleAlert, CircleCheck } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { McpTestResult } from "@/lib/api/mcpTestConfig";

/** Error codes with a short reason of their own (`McpTestErrorCode`). */
const REASONS = new Set([
  "url_refused",
  "spawn_failed",
  "exited",
  "timeout",
  "initialize_failed",
  "connect_failed",
  "stored_secret_not_released",
  "unsupported_transport",
]);

const seconds = (ms: number) => (ms / 1000).toFixed(1);

export function ConfigTestResult({ result }: { result: McpTestResult }) {
  const { t } = useTranslation();
  if (result.ok) {
    return (
      <Alert variant="success">
        <CircleCheck aria-hidden />
        <AlertTitle className="mb-0">
          {t("mcp.edit.testPassed", {
            seconds: seconds(result.latency_ms),
            tools: result.tool_count ?? 0,
            resources: result.resource_count ?? 0,
            prompts: result.prompt_count ?? 0,
          })}
        </AlertTitle>
      </Alert>
    );
  }
  const code = result.error_code ?? "";
  const reason = REASONS.has(code)
    ? t(`mcp.edit.testReason.${code}`, { code: result.exit_code ?? "?" })
    : t("mcp.edit.testReason.other");
  return (
    <Alert variant="error">
      <CircleAlert aria-hidden />
      <AlertTitle>
        {t("mcp.edit.testFailed", { seconds: seconds(result.latency_ms), reason })}
      </AlertTitle>
      <AlertDescription>
        {result.error_message ? `${result.error_message} ` : ""}
        {t("mcp.edit.nothingSaved")}
      </AlertDescription>
    </Alert>
  );
}
