// frontend/src/lib/knowledge/uploadChecks.ts — what the upload dialog says about a
// file: its kind, and why it is refused before or after it is sent (boards
// 5.1.18, 5.1.28).
import type { TFunction } from "i18next";

import { ApiError, translateApiError } from "@/lib/api/errors";

/** The upload bound (spec knowledge "Bound uploads and leave nothing behind
 *  on failure"). */
const MAX_BYTES = 20 * 1024 * 1024;

/** A file's kind as the dialog names it, from its extension. */
export const KINDS: Record<string, string> = {
  pdf: "PDF",
  doc: "Word",
  docx: "Word",
  ppt: "PowerPoint",
  pptx: "PowerPoint",
  xls: "Excel",
  xlsx: "Excel",
  html: "HTML",
  htm: "HTML",
  csv: "CSV",
  md: "Markdown",
  markdown: "Markdown",
  txt: "Text",
  zip: "ZIP archive",
  epub: "EPUB",
};

export function extensionOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i < 0 ? "" : name.slice(i + 1).toLowerCase();
}

interface Refusal {
  title: string;
  body: string;
}

/** Why a file is refused before it is sent, if it is. */
export function refuseBeforeSending(t: TFunction, file: File): Refusal | null {
  if (extensionOf(file.name) === "zip") {
    return { title: t("knowledge.upload.zipTitle"), body: t("knowledge.upload.zipBody") };
  }
  if (file.size > MAX_BYTES) {
    return { title: t("knowledge.upload.tooLargeTitle"), body: t("knowledge.upload.tooLargeBody") };
  }
  return null;
}

/** The daemon's refusal, in the dialog's words. */
export function refusalOf(t: TFunction, error: unknown, file: File | null): Refusal {
  if (error instanceof ApiError) {
    const reason = (error.details as { reason?: unknown } | undefined)?.reason;
    if (error.code === "KNOWLEDGE_UPLOAD_TOO_LARGE") {
      return {
        title: t("knowledge.upload.tooLargeTitle"),
        body: t("knowledge.upload.tooLargeBody"),
      };
    }
    if (reason === "scanned_pdf") {
      return { title: t("knowledge.upload.noTextTitle"), body: t("knowledge.upload.noTextBody") };
    }
    if (reason === "empty_conversion") {
      return {
        title: t("knowledge.upload.noTextAnyTitle"),
        body: t("knowledge.upload.noTextAnyBody"),
      };
    }
    if (reason === "unsupported_type") {
      const kind = file
        ? (KINDS[extensionOf(file.name)] ?? extensionOf(file.name).toUpperCase())
        : "";
      return {
        title: t("knowledge.upload.unsupportedTitle", { kind }),
        body: translateApiError(t, error),
      };
    }
  }
  return { title: t("knowledge.upload.failedTitle"), body: translateApiError(t, error) };
}
