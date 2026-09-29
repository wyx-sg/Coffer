// src/components/shell/SidebarLanguage.tsx — the language switcher at the foot of the sidebar; a globe popover on the rail.
import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export function SidebarLanguage({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        "border-t border-border",
        collapsed ? "flex justify-center p-2" : "px-5 py-2.5",
      )}
    >
      {collapsed ? (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("nav.language")}
              className="text-muted-foreground"
            >
              <Globe />
            </Button>
          </PopoverTrigger>
          <PopoverContent side="right" align="end" className="w-auto p-3">
            <LanguageSwitcher />
          </PopoverContent>
        </Popover>
      ) : (
        <LanguageSwitcher />
      )}
    </div>
  );
}
