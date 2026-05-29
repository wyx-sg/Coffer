// frontend/src/kinds/mcp/CapabilityList.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { SearchInput } from "@/components/SearchInput";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { components } from "@/lib/api/types";
import { useDisableCapability, useEnableCapability } from "@/lib/hooks/useMcpCapabilityMutations";

type ToolView = components["schemas"]["MCPToolView"];
type ResourceView = components["schemas"]["MCPResourceView"];
type PromptView = components["schemas"]["MCPPromptView"];
type CapabilityKind = "tool" | "resource" | "prompt";

interface Props {
  serverName: string;
  kind: CapabilityKind;
  tools?: ToolView[];
  resources?: ResourceView[];
  prompts?: PromptView[];
}

interface RowDescriptor {
  key: string;
  prefixed: string;
  description: string | null | undefined;
  enabled: boolean;
  schema?: Record<string, unknown>;
}

export function CapabilityList(props: Props) {
  const { t } = useTranslation();
  const { serverName, kind } = props;
  const enable = useEnableCapability();
  const disable = useDisableCapability();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  // Per-row in-flight state — toggling one capability must not disable the
  // switches on every other row in the list.
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(() => new Set());
  const rows = toRows(props);

  if (rows.length === 0) {
    const emptyKey =
      kind === "tool"
        ? "mcp.capabilities.emptyTool"
        : kind === "resource"
          ? "mcp.capabilities.emptyResource"
          : "mcp.capabilities.emptyPrompt";
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">{t(emptyKey)}</CardContent>
      </Card>
    );
  }

  const q = search.trim().toLowerCase();
  const filtered = rows.filter((row) => {
    if (q && !row.key.toLowerCase().includes(q)) return false;
    if (statusFilter === "enabled" && !row.enabled) return false;
    if (statusFilter === "disabled" && row.enabled) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput
          className="w-full sm:w-80"
          value={search}
          onChange={(v) => setSearch(v)}
          placeholder={t("mcp.capabilities.searchPlaceholder")}
          ariaLabel={t("mcp.capabilities.searchPlaceholder")}
        />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40" aria-label={t("mcp.capabilities.statusFilter")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("resources.status.all")}</SelectItem>
            <SelectItem value="enabled">{t("resources.status.enabled")}</SelectItem>
            <SelectItem value="disabled">{t("resources.status.disabled")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("mcp.capabilities.noMatches")}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {filtered.map((row) => (
            <CapabilityRow
              key={row.key}
              serverName={serverName}
              kind={kind}
              row={row}
              onToggle={(checked) => {
                const m = checked ? enable : disable;
                setPendingKeys((prev) => {
                  const next = new Set(prev);
                  next.add(row.key);
                  return next;
                });
                m.mutate(
                  {
                    serverName,
                    capabilityType: kind,
                    capabilityKey: row.key,
                  },
                  {
                    onSettled: () =>
                      setPendingKeys((prev) => {
                        const next = new Set(prev);
                        next.delete(row.key);
                        return next;
                      }),
                  },
                );
              }}
              mutating={pendingKeys.has(row.key)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function toRows(props: Props): RowDescriptor[] {
  if (props.kind === "tool" && props.tools) {
    return props.tools.map((t) => ({
      key: t.original_name,
      prefixed: t.prefixed_name,
      description: t.description,
      enabled: t.enabled,
      schema: t.input_schema as Record<string, unknown> | undefined,
    }));
  }
  if (props.kind === "resource" && props.resources) {
    return props.resources.map((r) => ({
      key: r.original_uri,
      prefixed: r.prefixed_uri,
      description: r.description,
      enabled: r.enabled,
    }));
  }
  if (props.kind === "prompt" && props.prompts) {
    return props.prompts.map((p) => ({
      key: p.original_name,
      prefixed: p.prefixed_name,
      description: p.description,
      enabled: p.enabled,
    }));
  }
  return [];
}

interface RowProps {
  serverName: string;
  kind: CapabilityKind;
  row: RowDescriptor;
  onToggle: (checked: boolean) => void;
  mutating: boolean;
}

function CapabilityRow({ row, kind, onToggle, mutating }: RowProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  return (
    <Card>
      <CardContent className="flex items-start gap-4 py-3">
        {row.schema ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="mt-0.5 size-7"
            onClick={() => setExpanded((v) => !v)}
            aria-label={
              expanded ? t("mcp.capabilities.collapseSchema") : t("mcp.capabilities.expandSchema")
            }
          >
            {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </Button>
        ) : (
          <div className="w-7" aria-hidden="true" />
        )}

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <code className="text-sm font-semibold">{row.key}</code>
            <Badge variant="outline" className="font-mono text-xs">
              {row.prefixed}
            </Badge>
          </div>
          {row.description ? (
            <p className="mt-1 text-sm text-muted-foreground">{row.description}</p>
          ) : null}
          {expanded && row.schema ? (
            <pre className="mt-2 overflow-auto rounded bg-muted p-2 text-xs">
              {JSON.stringify(row.schema, null, 2)}
            </pre>
          ) : null}
        </div>

        <Switch
          checked={row.enabled}
          onCheckedChange={onToggle}
          disabled={mutating}
          aria-label={t("mcp.capabilities.toggleAria", { kind, key: row.key })}
        />
      </CardContent>
    </Card>
  );
}
