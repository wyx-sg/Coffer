// src/components/mcp/server/McpPromptDetail.tsx — one prompt opened in the Prompts tab, one column like a tool's: what it does, its arguments, the name agents see, and the messages it fills to (design 4.1.12).
//
// A prompt's text is not listed: the server writes it when asked, from the
// arguments given. Each argument gets a field (required ones marked), and Get
// prompt asks the server for the messages those values make.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { components } from "@/lib/api/types";
import { useGetMcpPrompt } from "@/lib/hooks/useMcpCapabilityPreview";
import { McpPreviewResult } from "./McpPreviewResult";

type PromptView = components["schemas"]["MCPPromptView"];

interface Props {
  serverUid: string;
  prompt: PromptView;
}

export function McpPromptDetail({ serverUid, prompt }: Props) {
  const { t } = useTranslation();
  const fill = useGetMcpPrompt(serverUid);
  const [values, setValues] = useState<Record<string, string>>({});
  const missing = prompt.arguments.some((a) => a.required && !values[a.name]?.trim());
  const ask = () => {
    const args = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim() !== ""));
    fill.mutate({ name: prompt.original_name, args });
  };
  return (
    <div
      className="mb-2 ml-12 mr-2 flex flex-col gap-2 rounded-lg bg-surface-sunken px-3 py-2.5 text-xs"
      data-testid="mcp-prompt-detail"
    >
      {prompt.description ? <p className="text-text">{prompt.description}</p> : null}
      <div className="flex flex-col gap-1.5">
        <span className="font-label text-text-muted">{t("mcp.page.preview.arguments")}</span>
        {prompt.arguments.length === 0 ? (
          <span className="text-text-muted">{t("mcp.page.preview.noArguments")}</span>
        ) : (
          <ul className="flex flex-col gap-1.5" aria-label={t("mcp.page.preview.arguments")}>
            {prompt.arguments.map((a) => (
              <li key={a.name} className="grid grid-cols-[minmax(0,12rem)_1fr] items-start gap-3">
                <span className="flex min-w-0 flex-col gap-0.5 pt-1">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <code className="truncate font-mono text-text">{a.name}</code>
                    {a.required ? (
                      <Badge variant="secondary">{t("mcp.page.preview.required")}</Badge>
                    ) : null}
                  </span>
                  {a.description ? <span className="text-text-muted">{a.description}</span> : null}
                </span>
                <Input
                  aria-label={a.name}
                  value={values[a.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [a.name]: e.target.value }))}
                  className="h-control-sm text-xs"
                />
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="text-text-muted">
        {t("mcp.page.seenAs")} <code className="font-mono text-text">{prompt.prefixed_name}</code>
        {" · "}
        {t("mcp.page.characters", { count: prompt.client_name_length })}
      </p>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="font-label text-text-muted">{t("mcp.page.preview.messages")}</span>
          <Button size="sm" variant="secondary" disabled={fill.isPending || missing} onClick={ask}>
            {fill.isPending ? t("mcp.page.preview.getting") : t("mcp.page.preview.get")}
          </Button>
          {missing ? (
            <span className="text-text-muted">{t("mcp.page.preview.fillRequired")}</span>
          ) : null}
        </div>
        <McpPreviewResult result={fill.data} error={fill.error} />
      </div>
    </div>
  );
}
