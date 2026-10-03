// src/components/custom-tools/SpecError.tsx — why a spec could not be read, under the Spec field. A URL that
// did not answer gets its reason and the way to fix it, with a hand-off to an agent on the same line (the
// network is this machine's); a spec that did not parse names the line, and shows the text around it when
// Coffer holds the text (a file).
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { isUnreachable } from "@/lib/customTools/specErrors";
import { SpecViewer } from "./SpecViewer";

/** Lines shown each side of the one that failed. */
const AROUND = 3;

function detail(error: unknown, key: string): unknown {
  if (!(error instanceof ApiError)) return undefined;
  const details = error.details;
  return details && typeof details === "object"
    ? (details as Record<string, unknown>)[key]
    : undefined;
}

function hostOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

interface Props {
  error: unknown;
  /** The URL that was asked for. */
  url: string;
  /** The file being read: its name and text, when the spec came from a file. */
  file?: { name: string; text: string };
}

export function SpecError({ error, url, file }: Props) {
  const { t } = useTranslation();
  if (isUnreachable(error)) {
    const reason = String(detail(error, "reason") ?? "unreachable");
    const prompt = errorHandoff(error);
    return (
      <div className="flex items-start gap-2 text-xs text-danger" role="alert">
        <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1">
          {t("customTools.import.unreachable", {
            host: hostOf(url),
            reason: t(`customTools.import.reason.${reason}`, {
              defaultValue: t("customTools.import.reason.unreachable"),
            }),
          })}
        </span>
        {prompt ? <AgentHandoff prompt={prompt} size="sm" /> : null}
      </div>
    );
  }
  const line = detail(error, "line");
  const lines = file?.text.split("\n") ?? [];
  const snippet =
    typeof line === "number" && file && line >= 1 && line <= lines.length
      ? { from: Math.max(1, line - AROUND), to: Math.min(lines.length, line + AROUND), line }
      : null;
  return (
    <>
      <p role="alert" className="flex items-start gap-1.5 text-xs text-danger">
        <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>
          {error instanceof ApiError && error.code === "OPENAPI_UNREADABLE"
            ? t("customTools.import.readFailed", { reason: error.envelopeMessage })
            : translateApiError(t, error)}
        </span>
      </p>
      {snippet && file ? (
        <SpecViewer
          path={`${file.name} · ${t("customTools.import.line", { line: snippet.line })}`}
          text={lines.slice(snippet.from - 1, snippet.to).join("\n")}
          startLine={snippet.from}
          mark={snippet.line}
        />
      ) : null}
    </>
  );
}
