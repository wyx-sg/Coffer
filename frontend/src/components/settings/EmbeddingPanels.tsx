// components/settings/EmbeddingPanels.tsx — presentational pieces of the global
// Embedding settings card (spec knowledge FR-077): the "pick a provider, then
// pick a model" block — deliberately the same two Selects the internal-engine
// card above it has, because it is the same question — and the chunking-defaults
// block that also hosts the enable switch. Kept apart from EmbeddingSettings so
// the page stays small; all state lives in the page.
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { TestResult } from "@/lib/hooks/useModelIntrospection";

export function EmbeddingModelFields({
  connections,
  connection,
  onConnectionChange,
  model,
  onModelChange,
  /** The embedding models the chosen connection offers, in its own order. */
  modelOptions,
  /** Shown under the model Select when the connection offers no model to pick. */
  modelsHint,
  /** True while nothing is configured — the fallback-to-keyword/grep notice. */
  notConfigured,
  dimensions,
  onDimensionsChange,
  onDimensionsCommit,
  onTest,
  testPending,
  testResult,
  disabled,
}: {
  connections: string[];
  connection: string;
  onConnectionChange: (v: string) => void;
  model: string;
  onModelChange: (v: string) => void;
  modelOptions: string[];
  modelsHint?: string;
  notConfigured?: boolean;
  dimensions: number;
  onDimensionsChange: (v: number) => void;
  onDimensionsCommit: () => void;
  onTest: () => void;
  testPending: boolean;
  testResult: TestResult | null;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const commitOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
  };
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label>{t("settings.embedding.connection")}</Label>
          <Select
            value={connection}
            onValueChange={onConnectionChange}
            disabled={disabled || connections.length === 0}
          >
            <SelectTrigger aria-label={t("settings.embedding.connection")}>
              <SelectValue placeholder={t("settings.embedding.connectionPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {connections.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label>{t("settings.embedding.model")}</Label>
          <Select
            value={model}
            onValueChange={onModelChange}
            disabled={disabled || connection === "" || modelOptions.length === 0}
          >
            <SelectTrigger aria-label={t("settings.embedding.model")}>
              <SelectValue placeholder={t("settings.embedding.modelPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {modelOptions.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {modelsHint ? <p className="text-xs text-amber-600">{modelsHint}</p> : null}
        </div>
      </div>

      {notConfigured ? (
        <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
          {t("settings.embedding.empty")}
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="emb-dims">{t("settings.embedding.dimensions")}</Label>
          <Input
            id="emb-dims"
            type="number"
            value={dimensions}
            disabled={disabled}
            onChange={(e) => onDimensionsChange(Number(e.target.value) || 0)}
            onBlur={onDimensionsCommit}
            onKeyDown={commitOnEnter}
          />
        </div>
        <div className="flex items-end gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onTest}
            disabled={testPending || connection === "" || model === ""}
          >
            {testPending && <Loader2 className="mr-1 size-3.5 animate-spin" />}
            {t("settings.models.testConnection")}
          </Button>
          {testResult && (
            <span
              className={`flex items-center gap-1 pb-2 text-xs ${
                testResult.ok ? "text-green-600" : "text-destructive"
              }`}
              role="status"
            >
              {testResult.ok ? (
                <CheckCircle2 className="size-3.5" />
              ) : (
                <XCircle className="size-3.5" />
              )}
              {testResult.message}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function EmbeddingChunkingFields({
  enabled,
  onEnabledChange,
  chunkSize,
  onChunkSizeChange,
  onChunkSizeCommit,
  chunkOverlap,
  onChunkOverlapChange,
  onChunkOverlapCommit,
  disabled,
}: {
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  chunkSize: number;
  onChunkSizeChange: (v: number) => void;
  /** Persist the chunk size once editing finishes (blur / Enter). */
  onChunkSizeCommit: () => void;
  chunkOverlap: number;
  onChunkOverlapChange: (v: number) => void;
  /** Persist the chunk overlap once editing finishes (blur / Enter). */
  onChunkOverlapCommit: () => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  // Blur on Enter so the commit handler fires from a single code path.
  const commitOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
  };
  return (
    <div className="space-y-3 border-t border-border pt-4">
      <div>
        <Label>{t("settings.embedding.chunkingTitle")}</Label>
        <p className="text-xs text-muted-foreground">{t("settings.embedding.chunkingHint")}</p>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
        <div>
          <Label>{t("settings.embedding.enabled")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.embedding.enabledHint")}</p>
        </div>
        <Switch checked={enabled} onCheckedChange={onEnabledChange} disabled={disabled} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="emb-chunk-size">{t("settings.embedding.chunkSize")}</Label>
          <Input
            id="emb-chunk-size"
            type="number"
            value={chunkSize}
            disabled={disabled}
            onChange={(e) => onChunkSizeChange(Number(e.target.value) || 0)}
            onBlur={onChunkSizeCommit}
            onKeyDown={commitOnEnter}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="emb-chunk-overlap">{t("settings.embedding.chunkOverlap")}</Label>
          <Input
            id="emb-chunk-overlap"
            type="number"
            value={chunkOverlap}
            disabled={disabled}
            onChange={(e) => onChunkOverlapChange(Number(e.target.value) || 0)}
            onBlur={onChunkOverlapCommit}
            onKeyDown={commitOnEnter}
          />
        </div>
      </div>
    </div>
  );
}
