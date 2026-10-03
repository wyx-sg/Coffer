// src/components/custom-tools/ResponseViewer.tsx — a test response in the shared viewer (Foundations 0.6.03): a bar
// with "Response · <content type>" and Copy, an optional note at the top when the response was cut short, then the
// body with line numbers and syntax colours. It sits outside the result block, under it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, TriangleAlert } from "lucide-react";

import { CodeView } from "@/components/preview/CodeView";
import { Button } from "@/components/ui/button";
import type { PreviewLanguage } from "@/lib/preview/language";

interface Props {
  body: string;
  contentType: string | null;
  /** The size the response was cut at ("1 MB"); `null` when it came whole. */
  cutAt: string | null;
}

function languageOf(contentType: string | null): PreviewLanguage {
  if (!contentType) return "text";
  if (contentType.includes("json")) return "json";
  if (contentType.includes("html")) return "html";
  if (contentType.includes("xml")) return "xml";
  return "text";
}

/** JSON reads best indented; a body that does not parse (or was cut) is shown as it came. */
function shown(body: string, language: PreviewLanguage): string {
  if (language !== "json") return body;
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}

export function ResponseViewer({ body, contentType, cutAt }: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const language = languageOf(contentType);
  const copy = () => {
    void navigator.clipboard?.writeText(body).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div
      className="overflow-hidden rounded-lg border border-border-subtle"
      data-testid="custom-tool-response"
    >
      <div className="flex h-9 items-center gap-2 border-b border-border-subtle bg-surface-sunken pl-3 pr-1.5">
        <span className="min-w-0 flex-1 truncate text-xs font-label text-text">
          {contentType
            ? t("customTools.test.responseType", { type: contentType.split(";")[0] })
            : t("customTools.test.response")}
        </span>
        <Button type="button" variant="ghost" size="sm" onClick={copy}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          {t("common.copy")}
        </Button>
      </div>
      {cutAt ? (
        <div className="flex min-h-8 items-start gap-2 border-b border-border-subtle bg-surface-sunken px-3 py-1.5 text-xs">
          <TriangleAlert className="mt-px size-3.5 shrink-0 text-warning" aria-hidden />
          <span>
            <span className="font-label text-text">{t("customTools.test.cutShort", { size: cutAt })}</span>{" "}
            <span className="text-text-muted">{t("customTools.test.cutShortBody", { size: cutAt })}</span>
          </span>
        </div>
      ) : null}
      <CodeView
        value={shown(body, language)}
        language={language}
        maxHeight="16rem"
        ariaLabel={t("customTools.test.response")}
        className="rounded-none border-0"
      />
    </div>
  );
}
