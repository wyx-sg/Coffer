// src/components/custom-tools/SpecField.tsx — the Spec field of an import: a URL | File switch on its own
// line, then a URL with Load (→ Loading… → Reload) or a file read in the browser, and one result line.
import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Check, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { OpenApiReading } from "@/lib/api/customTools";
import { cn } from "@/lib/utils";
import type { SpecMode } from "./addFlow";
import { isUnreachable } from "@/lib/customTools/specErrors";
import { SpecError } from "./SpecError";

/** The largest document the daemon reads. */
export const MAX_SPEC_BYTES = 5 * 1024 * 1024;

interface Props {
  mode: SpecMode;
  onMode: (mode: SpecMode) => void;
  url: string;
  onUrl: (url: string) => void;
  fileName: string;
  /** Load the URL. */
  onLoad: () => void;
  /** A file was picked: its name and text. */
  onFile: (name: string, text: string) => void;
  /** A file too large to send. */
  onFileTooLarge: () => void;
  loading: boolean;
  reading: OpenApiReading | null;
  error: unknown;
  /** The file's text, to show the lines around a parse failure. */
  fileText?: string;
}

export function SpecField(props: Props) {
  const { mode, url, loading, reading, error } = props;
  const { t } = useTranslation();
  const id = useId();
  const fileInput = useRef<HTMLInputElement>(null);

  const segment = (value: SpecMode, label: string) => (
    <button
      type="button"
      role="radio"
      aria-checked={mode === value}
      onClick={() => props.onMode(value)}
      className={cn(
        "h-[22px] rounded-sm px-3 text-xs font-label transition-colors duration-fast",
        mode === value
          ? "bg-surface-raised text-text shadow-lifted"
          : "text-text-muted hover:text-text",
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`${id}-spec`} required>
        {t("customTools.fields.spec")}
      </Label>
      <div
        role="radiogroup"
        aria-label={t("customTools.fields.specSource")}
        className="inline-flex w-fit rounded-md bg-surface-sunken p-[3px]"
      >
        {segment("url", t("customTools.fields.specUrl"))}
        {segment("file", t("customTools.fields.specFile"))}
      </div>
      {mode === "url" ? (
        <div className="flex gap-2">
          <Input
            id={`${id}-spec`}
            className="flex-1 font-mono"
            value={url}
            aria-invalid={error && mode === "url" ? true : undefined}
            placeholder="https://"
            onChange={(e) => props.onUrl(e.target.value)}
          />
          <Button variant="outline" disabled={loading || url.trim() === ""} onClick={props.onLoad}>
            {reading && !loading && !error ? <RotateCw aria-hidden /> : null}
            {loading
              ? t("customTools.import.loading")
              : isUnreachable(error)
                ? t("common.retry")
                : reading
                  ? t("customTools.import.reload")
                  : t("customTools.import.load")}
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <input
            ref={fileInput}
            id={`${id}-spec`}
            type="file"
            accept=".json,.yaml,.yml,application/json,application/yaml"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              if (file.size > MAX_SPEC_BYTES) return props.onFileTooLarge();
              void file.text().then((text) => props.onFile(file.name, text));
            }}
          />
          <Button variant="outline" disabled={loading} onClick={() => fileInput.current?.click()}>
            {t("customTools.import.browse")}
          </Button>
          <span className="min-w-0 truncate font-mono text-xs text-text-muted">
            {props.fileName || t("customTools.import.fileHelp")}
          </span>
        </div>
      )}
      {error ? (
        <SpecError
          error={error}
          url={url}
          file={
            mode === "file" && props.fileText
              ? { name: props.fileName, text: props.fileText }
              : undefined
          }
        />
      ) : loading ? (
        <p className="text-xs text-text-muted">{t("customTools.import.fetching")}</p>
      ) : reading ? (
        <p className="inline-flex items-center gap-1 text-xs text-success">
          <Check className="size-3.5" aria-hidden />
          {[
            t("customTools.import.loaded", { count: reading.operations.length }),
            [reading.title, reading.version].filter(Boolean).join(" "),
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      ) : (
        <p className="text-xs text-text-muted">
          {mode === "url" ? t("customTools.import.urlHelp") : t("customTools.import.fileHelp")}
        </p>
      )}
    </div>
  );
}
