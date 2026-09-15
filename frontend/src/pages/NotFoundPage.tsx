// src/pages/NotFoundPage.tsx — the catch-all route: names the unmatched path
// and offers one way back (home).
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, SearchX } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  return (
    <div className="space-y-6">
      <PageHeader
        icon={SearchX}
        title={t("notFound.title")}
        subtitle={t("notFound.subtitle", { path: pathname })}
      />
      <EmptyState
        icon={SearchX}
        title={t("notFound.bodyTitle")}
        description={t("notFound.body")}
        action={
          <Button asChild variant="outline" size="sm">
            <Link to="/">
              <ArrowLeft className="mr-1 size-4" />
              {t("notFound.cta")}
            </Link>
          </Button>
        }
      />
    </div>
  );
}
