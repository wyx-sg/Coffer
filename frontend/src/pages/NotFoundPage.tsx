// src/pages/NotFoundPage.tsx — the catch-all route (board 1.2.16): names the unmatched address, suggests the closest page, and offers Overview and ⌘K.
//
// The behaviour sheet (1.2.20): "Unknown route: 404 with a closest-match
// suggestion and ⌘K." The suggestion is the page whose address is nearest the
// first segment of the one typed (`/mcp/sentri` → MCP servers), so a stale or
// mistyped link is one click from where it meant to go.
import { useTranslation, Trans } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { Compass, Search } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { requestPalette } from "@/components/shell/paletteRequest";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { closestPage } from "@/lib/navigation";
import { shortcutLabel } from "@/lib/shortcuts";

export function NotFoundPage() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const suggestion = closestPage(pathname);
  const mono = <span className="font-mono text-xs text-text" />;
  return (
    <EmptyState
      size="page"
      icon={Compass}
      title={t("notFound.title")}
      action={
        <Button asChild>
          <Link to="/">{t("notFound.cta")}</Link>
        </Button>
      }
      secondaryAction={
        <Button variant="outline" onClick={requestPalette}>
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
          className="mt-3 flex items-center gap-2.5 rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2.5 text-sm transition-colors duration-fast hover:bg-surface-hover"
        >
          <span className="text-text-muted">{t("notFound.didYouMean")}</span>
          <span className="font-mono text-xs text-accent-text">{suggestion}</span>
        </Link>
      ) : null}
    </EmptyState>
  );
}
