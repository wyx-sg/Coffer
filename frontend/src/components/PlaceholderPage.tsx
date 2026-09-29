// src/components/PlaceholderPage.tsx — PLACEHOLDER: the body of a sidebar page whose content has not landed yet.
//
// The shell (change revise-web-ui-ia) fixes every sidebar entry and route at
// once, but some pages arrive with their own work item later in the same
// release: Overview, Custom tools, CLIs, Secrets and Usage. Until then each of
// those routes renders this — the page's real title, so the sidebar and the
// page still share one name, and an empty state saying the page is coming in
// this release. Each caller is replaced by its page when its work item lands;
// delete this component with the last one.
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

interface Props {
  icon: LucideIcon;
  /** The page's title key — the same words as its sidebar entry. */
  titleKey: string;
}

export function PlaceholderPage({ icon, titleKey }: Props) {
  const { t } = useTranslation();
  return (
    <div className="space-y-6" data-testid="placeholder-page">
      <PageHeader icon={icon} title={t(titleKey)} />
      <EmptyState
        icon={icon}
        title={t("placeholder.title")}
        description={t("placeholder.description")}
      />
    </div>
  );
}
