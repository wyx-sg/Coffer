// frontend/src/components/mcp/add/AddTestResult.tsx — what testing the Add
// server form found, above Available to (boards Mcp-Add-TestPassed,
// Mcp-Add-Http, Mcp-Add-Errors).
//
// Passed: "Test passed in 1.4 s · 26 tools, 0 resources, 0 prompts" (stdio) or
// "Connected in 212 ms · …" (HTTP), the first tool names, a warning for a name
// longer than model APIs accept, and the stderr lines behind Show. Failed: why,
// and the last lines the process printed on stderr.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert, CircleCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { McpTestResult } from "@/lib/api/mcpTestConfig";
import { cn } from "@/lib/utils";

/** How many tool names the result lists before "+ N more". */
const SHOWN = 7;
/** The longest tool name model APIs accept. */
const NAME_LIMIT = 64;

const seconds = (ms: number) => (ms / 1000).toFixed(1);

function Stderr({ lines }: { lines: string[] }) {
  return (
    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-surface px-2.5 py-2 font-mono text-2xs leading-relaxed text-text">
      {lines.join("\n")}
    </pre>
  );
}

interface Props {
  result: McpTestResult;
  transport: "stdio" | "http";
  /** The server's name, for the name agents see each tool under. */
  server: string;
}

export function AddTestResult({ result, transport, server }: Props) {
  const { t } = useTranslation();
  const [showStderr, setShowStderr] = useState(false);
  const stderr = result.stderr_tail ?? [];

  if (!result.ok) {
    const exited = result.error_code === "exited";
    return (
      <div
        role="status"
        data-testid="add-test-result"
        className="flex flex-col gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-xs"
      >
        <p className="flex items-center gap-2 font-label text-sm text-danger">
          <CircleAlert aria-hidden className="size-4 shrink-0" />
          {exited
            ? t("mcp.add.test.failedExited", {
                seconds: seconds(result.latency_ms),
                code: result.exit_code ?? "?",
              })
            : t("mcp.add.test.failed", { seconds: seconds(result.latency_ms) })}
        </p>
        <p className="text-text">
          {exited
            ? result.tool_count > 0
              ? t("mcp.add.test.stderrIntro")
              : t("mcp.add.test.exitedBody")
            : result.error_code === "stored_secret_not_released"
              ? t("mcp.add.test.storedSecret", {
                  keys: (result.unreleased_secret_keys ?? []).join(", "),
                })
              : (result.error_message ?? "")}
          {!exited && stderr.length > 0 ? ` ${t("mcp.add.test.stderrIntro")}` : ""}
        </p>
        {stderr.length > 0 ? <Stderr lines={stderr} /> : null}
      </div>
    );
  }

  const tools = result.tools ?? [];
  const long = tools.find((tool) => `mcp__coffer__${server}__${tool.name}`.length > NAME_LIMIT);
  const head =
    transport === "http"
      ? t("mcp.add.test.connected", { ms: result.latency_ms })
      : t("mcp.add.test.passed", { seconds: seconds(result.latency_ms) });
  return (
    <div
      role="status"
      data-testid="add-test-result"
      className="flex flex-col gap-2 rounded-lg bg-success-soft px-3 py-2.5 text-xs"
    >
      <p className="flex items-center gap-2 text-sm text-text">
        <CircleCheck aria-hidden className="size-4 shrink-0 text-success" />
        <span>
          <span className="font-label">{head}</span>
          {" · "}
          {t("mcp.add.test.counts", {
            tools: result.tool_count,
            resources: result.resource_count ?? 0,
            prompts: result.prompt_count ?? 0,
          })}
        </span>
      </p>
      {tools.length > 0 ? (
        <p className="flex flex-wrap gap-1.5">
          {tools.slice(0, SHOWN).map((tool) => (
            <span
              key={tool.name}
              className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-2xs"
            >
              {tool.name}
            </span>
          ))}
          {tools.length > SHOWN ? (
            <span className="px-1 py-0.5 text-text-muted">
              {t("mcp.add.test.more", { count: tools.length - SHOWN })}
            </span>
          ) : null}
        </p>
      ) : null}
      {long ? (
        <p className="text-warning">
          {t("mcp.add.test.longName", {
            name: long.name,
            length: `mcp__coffer__${server}__${long.name}`.length,
            limit: NAME_LIMIT,
          })}
        </p>
      ) : null}
      {transport === "http" ? (
        <p className="text-text-muted">{t("mcp.add.test.allOn", { count: result.tool_count })}</p>
      ) : null}
      {stderr.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <p className={cn("flex items-center gap-2 text-text-muted")}>
            {t("mcp.add.test.stderrLines", { count: stderr.length })}
            <Button
              variant="link"
              size="sm"
              className="h-auto px-0 text-xs"
              aria-expanded={showStderr}
              onClick={() => setShowStderr((v) => !v)}
            >
              {showStderr ? t("mcp.add.test.hide") : t("mcp.add.test.show")}
            </Button>
          </p>
          {showStderr ? <Stderr lines={stderr} /> : null}
        </div>
      ) : null}
    </div>
  );
}
