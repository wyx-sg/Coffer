// src/components/providers/ModelProvidersHeader.tsx — the one header of Model providers: title, subtitle, Add provider, and the Providers | Usage tabs.
//
// Both tabs sit under this same header (canvas 2.2.01 / 2.2.19): Add provider
// is the page's one primary button whichever tab is open, and the tab rail's
// hairline runs the full width of the page. The tab is the address:
// `/model-providers` and `/model-providers/<uid>` are Providers,
// `/model-providers?tab=usage` is Usage. Switching is a replace-navigation, so
// the tab does not pile up history.
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { providersTabPath, type ProvidersTab } from "@/lib/providers/tabs";
import { PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { cn } from "@/lib/utils";

interface Props {
  tab: ProvidersTab;
  onAdd: () => void;
}

export function ModelProvidersHeader({ tab, onAdd }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="shrink-0">
      <div className={cn(PAGE_BLEED_HEAD, "pb-3")}>
        <PageHeader
          title={t("providers.title")}
          subtitle={t("providers.subtitle")}
          actions={
            <Button onClick={onAdd}>
              <Plus aria-hidden /> {t("providers.add.open")}
            </Button>
          }
        />
      </div>
      <Tabs
        value={tab}
        onValueChange={(next) => {
          if (next !== tab) navigate(providersTabPath(next as ProvidersTab), { replace: true });
        }}
        className="border-b border-border px-8"
      >
        <TabsList className="border-b-0">
          <TabsTrigger value="providers">{t("providers.tabs.providers")}</TabsTrigger>
          <TabsTrigger value="usage">{t("providers.tabs.usage")}</TabsTrigger>
        </TabsList>
      </Tabs>
    </div>
  );
}
