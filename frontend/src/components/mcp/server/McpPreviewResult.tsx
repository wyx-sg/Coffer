// src/components/mcp/server/McpPreviewResult.tsx — what a resource read or a filled prompt answered, inside its row's details (design 4.1.11, 4.1.12).
//
// Each body or message in a box that scrolls past a fixed height, JSON laid
// out, text cut at 64 KB said so, a binary body named by its type and size
// and never shown. The server's own error, or why it could not be asked,
// reads in place of the contents.
import { useTranslation } from "react-i18next";

import type { CapabilityPreview } from "@/lib/api/mcpServers";
import { translateApiError } from "@/lib/api/errors";

type Content = CapabilityPreview["contents"][number];

/** JSON laid out for reading; anything else as it came. */
function readable(content: Content): string {
  const text = content.text ?? "";
  if (content.truncated) return text;
  const looksJson = content.mime_type?.includes("json") || /^\s*[[{]/.test(text);
  if (!looksJson) return text;
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

function Body({ content }: { content: Content }) {
  const { t } = useTranslation();
  if (content.text === null || content.text === undefined)
    return (
      <p className="text-text-muted">
        {t("mcp.page.preview.binary", {
          type: content.mime_type ?? content.kind,
          size: content.size_bytes ?? "?",
        })}
      </p>
    );
  return (
    <div className="flex flex-col gap-1">
      <pre
        className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border-subtle bg-surface-raised px-2.5 py-2 font-mono text-2xs text-text"
        data-testid="mcp-preview-text"
      >
        {readable(content)}
      </pre>
      {content.truncated ? (
        <p className="text-text-muted">{t("mcp.page.preview.truncated")}</p>
      ) : null}
    </div>
  );
}

interface Props {
  result: CapabilityPreview | undefined;
  error: unknown;
}

export function McpPreviewResult({ result, error }: Props) {
  const { t } = useTranslation();
  if (error) return <p className="text-danger">{translateApiError(t, error)}</p>;
  if (!result) return null;
  if (result.error)
    return (
      <p className="text-danger">{t("mcp.page.preview.serverError", { error: result.error })}</p>
    );
  if (result.contents.length === 0)
    return <p className="text-text-muted">{t("mcp.page.preview.empty")}</p>;
  return (
    <div className="flex flex-col gap-2" data-testid="mcp-preview-result">
      {result.contents.map((c, i) => (
        <div key={i} className="flex flex-col gap-1">
          {c.role ? (
            <span className="font-label text-text-muted">
              {t(`mcp.page.preview.role.${c.role === "assistant" ? "assistant" : "user"}`)}
            </span>
          ) : null}
          <Body content={c} />
        </div>
      ))}
    </div>
  );
}
