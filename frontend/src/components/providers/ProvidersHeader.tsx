// src/components/providers/ProvidersHeader.tsx — the Model providers header: title, Experimental tag, description, Add provider, and the Providers | Usage tabs.
//
// Both tabs share it (Agents 2.2): the Usage tab is `/model-providers?tab=usage`,
// the Providers tab the bare list and any `/model-providers/<uid>`. Switching
// is a replace-navigation, so the tab does not pile up history.
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { providersTabPath, type ProvidersTab } from "@/lib/providers/tabs";
import { cn } from "@/lib/utils";

interface Props {
  tab: ProvidersTab;
  onAdd: () => void;
  /** The tab rail runs edge to edge inside a full-bleed workspace. */
  bleed?: boolean;
}

export function ProvidersHeader({ tab, onAdd, bleed }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        title={t("providers.title")}
        subtitle={t("providers.subtitle")}
        experimental
        actions={
          <Button onClick={onAdd}>
            <Plus aria-hidden /> {t("providers.add.open")}
          </Button>
        }
      />
      <Tabs
        value={tab}
        onValueChange={(next) => {
          if (next !== tab) navigate(providersTabPath(next as ProvidersTab), { replace: true });
        }}
      >
        <TabsList className={cn(bleed && "-mx-6 px-6")}>
          {(["providers", "usage"] as const).map((name) => (
            <TabsTrigger key={name} value={name}>
              {t(`providers.tabs.${name}`)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
    </div>
  );
}
