import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Database,
  Info,
  Laptop,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { isTauri } from "@/lib/tauri";
import { cn } from "@/lib/utils";

interface Item {
  to: string;
  labelKey: string;
  icon: LucideIcon;
}

const GENERAL_ITEM: Item = {
  to: "/settings/general",
  labelKey: "settings.tabs.general",
  icon: SlidersHorizontal,
};
const MODELS_ITEM: Item = {
  to: "/settings/models",
  labelKey: "settings.tabs.models",
  icon: Bot,
};
const DATA_ITEM: Item = {
  to: "/settings/data",
  labelKey: "settings.tabs.data",
  icon: Database,
};
const APP_ITEM: Item = {
  to: "/settings/app",
  labelKey: "settings.tabs.app",
  icon: Laptop,
};
const SECURITY_ITEM: Item = {
  to: "/settings/security",
  labelKey: "settings.tabs.security",
  icon: ShieldCheck,
};
const ABOUT_ITEM: Item = {
  to: "/settings/about",
  labelKey: "settings.tabs.about",
  icon: Info,
};

export function SettingsLayout() {
  const { t } = useTranslation();
  // The App tab (launch-at-login) is desktop-only — it is hidden in the
  // browser, where those Tauri capabilities don't exist.
  const items: Item[] = isTauri()
    ? [GENERAL_ITEM, MODELS_ITEM, DATA_ITEM, SECURITY_ITEM, APP_ITEM, ABOUT_ITEM]
    : [GENERAL_ITEM, MODELS_ITEM, DATA_ITEM, SECURITY_ITEM, ABOUT_ITEM];

  return (
    <div className="space-y-8">
      <PageHeader icon={Settings} title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <div className="flex flex-col gap-6 md:flex-row">
        <nav className="md:w-52 md:shrink-0" aria-label={t("settings.title")}>
          <div className="flex gap-1 overflow-x-auto md:flex-col md:gap-0.5">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-foreground/80 hover:bg-secondary hover:text-foreground",
                  )
                }
              >
                <item.icon className="size-4 shrink-0" strokeWidth={1.75} />
                <span>{t(item.labelKey)}</span>
              </NavLink>
            ))}
          </div>
        </nav>
        <div className="min-w-0 flex-1">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
