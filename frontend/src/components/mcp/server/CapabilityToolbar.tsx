// src/components/mcp/server/CapabilityToolbar.tsx — the toolbar over the Tools, Resources and Prompts tables (design 4.1.10–4.1.12).
//
// Search on the left; on the right "N of M on" and All on · All off. The tab
// is already named by the tab strip, so the toolbar carries no title.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";

interface Props {
  placeholder: string;
  query: string;
  onQueryChange: (query: string) => void;
  on: number;
  total: number;
  busy: boolean;
  onAllOn: () => void;
  onAllOff: () => void;
  /** Extra controls before the counts (the Tools tab's exposure menu). */
  extra?: ReactNode;
}

export function CapabilityToolbar({
  placeholder,
  query,
  onQueryChange,
  on,
  total,
  busy,
  onAllOn,
  onAllOff,
  extra,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <SearchInput
        value={query}
        onChange={onQueryChange}
        placeholder={placeholder}
        ariaLabel={placeholder}
        className="w-64"
      />
      <span className="ml-auto inline-flex items-center gap-1">
        {extra}
        <span className="mr-1 text-xs text-text-muted" data-testid="mcp-caps-on">
          {t("mcp.page.nOfMOn", { on, total })}
        </span>
        <Button
          variant="link"
          size="sm"
          disabled={busy || total === 0 || on === total}
          onClick={onAllOn}
        >
          {t("mcp.page.allOn")}
        </Button>
        <span aria-hidden className="text-text-subtle">
          ·
        </span>
        <Button variant="link" size="sm" disabled={busy || on === 0} onClick={onAllOff}>
          {t("mcp.page.allOff")}
        </Button>
      </span>
    </div>
  );
}
