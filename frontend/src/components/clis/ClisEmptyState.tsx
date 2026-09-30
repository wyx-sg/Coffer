// src/components/clis/ClisEmptyState.tsx — the CLIs page before any skill declares `requires:`.
import { ExternalLink, SquareTerminal } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

export function ClisEmptyState() {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={SquareTerminal}
      title={t("clis.empty.title")}
      description={t("clis.empty.description")}
      action={
        <Button variant="outline" asChild>
          <a href={t("clis.empty.docsUrl")} target="_blank" rel="noreferrer">
            <ExternalLink aria-hidden />
            {t("clis.empty.docs")}
          </a>
        </Button>
      }
    />
  );
}
