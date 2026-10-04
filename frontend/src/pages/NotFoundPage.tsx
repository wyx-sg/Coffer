// src/pages/NotFoundPage.tsx — the catch-all route (board 1.1.17): names the unmatched address, suggests the closest page, and offers Overview and ⌘K.
//
// The behaviour sheet (1.1.04, "Errors & not found"): "Unknown route: 404 with
// a closest-match suggestion and ⌘K." Back to Overview is the outline button,
// Search Coffer ⌘K the ghost one; the suggestion is a bordered card with a
// 28px tile, "Did you mean" over the path, and a trailing chevron. The suggestion is the page whose address is nearest the
// first segment of the one typed (`/mcp/sentri` → MCP servers), so a stale or
// mistyped link is one click from where it meant to go.
import { useTranslation, Trans } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { ChevronLeft, ChevronRight, Compass, Search } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { requestPalette } from "@/components/shell/paletteRequest";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { closestPage, NAV_ENTRIES } from "@/lib/navigation";
import { shortcutLabel } from "@/lib/shortcuts";

export function NotFoundPage() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const suggestion = closestPage(pathname);
  // The suggested page's own sidebar icon marks the card.
  const SuggestionIcon = NAV_ENTRIES.find((e) => e.to === suggestion)?.icon ?? Compass;
  const mono = <span className="font-mono text-xs text-text" />;
  return (
    <EmptyState
      size="page"
      icon={Compass}
      title={t("notFound.title")}
      className="max-w-[440px]"
      action={
        <Button asChild variant="outline">
          <Link to="/">
            <ChevronLeft aria-hidden />
            {t("notFound.cta")}
          </Link>
        </Button>
      }
      secondaryAction={
        <Button variant="ghost" onClick={requestPalette}>
          <Search aria-hidden />
          {t("notFound.search")}
          <Kbd aria-hidden>{shortcutLabel("k")}</Kbd>
        </Button>
      }
    >
      <p className="text-center text-sm leading-normal text-text-muted">
        <Trans i18nKey="notFound.body" values={{ path: pathname }} components={{ mono }} />
      </p>
      {suggestion ? (
        <Link
          to={suggestion}
          className="mt-3 flex w-full items-center gap-2.5 rounded-[10px] border border-border bg-surface-raised px-3.5 py-2.5 transition-colors duration-fast hover:bg-surface-hover"
        >
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
            <SuggestionIcon className="size-3.5" strokeWidth={1.75} aria-hidden />
          </span>
          <span className="flex min-w-0 grow flex-col gap-0.5 text-left">
            <span className="text-xs text-text-muted">{t("notFound.didYouMean")}</span>
            <span className="truncate font-mono text-xs text-text">{suggestion}</span>
          </span>
          <ChevronRight
            className="size-[15px] shrink-0 text-text-subtle"
            strokeWidth={1.75}
            aria-hidden
          />
        </Link>
      ) : null}
    </EmptyState>
  );
}
