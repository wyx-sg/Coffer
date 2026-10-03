// src/components/providers/ModelProvidersHeader.tsx — the one header of Model providers: title, Experimental, subtitle, Add provider, and the Providers | Usage tabs.
//
// Both tabs sit under this same header (canvas 2.2.01 / 2.2.19): Add provider
// is the page's one primary button whichever tab is open, and the tab rail's
// hairline runs the full width of the page. The tab is the address:
// `/model-providers` and `/model-providers/<uid>` are Providers,
// `/model-providers/usage` is Usage.
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ExperimentalTag } from "@/components/ExperimentalTag";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type ModelProvidersTab = "providers" | "usage";

const MODEL_PROVIDERS_PATH = "/model-providers";
export const USAGE_PATH = "/model-providers/usage";

interface Props {
  tab: ModelProvidersTab;
  onAdd: () => void;
}

export function ModelProvidersHeader({ tab, onAdd }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="shrink-0">
      <div className="px-8 pb-3 pt-4">
        <PageHeader
          title={t("providers.title")}
          badges={<ExperimentalTag />}
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
        onValueChange={(next) => navigate(next === "usage" ? USAGE_PATH : MODEL_PROVIDERS_PATH)}
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
