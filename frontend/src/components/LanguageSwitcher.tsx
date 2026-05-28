import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";
import { cn } from "@/lib/utils";

const LANGS: Array<{ code: "en" | "zh"; label: string }> = [
  { code: "en", label: "EN" },
  { code: "zh", label: "中" },
];

/**
 * The sidebar-footer language picker — the single language control in the
 * app. Implemented as a button group rather than a combobox so it doesn't
 * collide with other comboboxes on the page (e.g. the audit / invocations
 * filters) — Playwright's `getByRole("combobox")` is unscoped and would
 * match multiple controls if this used the same role.
 */
export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const current = i18n.language.startsWith("zh") ? "zh" : "en";
  return (
    <div
      className="flex items-center gap-1.5 text-xs text-muted-foreground"
      role="group"
      aria-label={t("nav.language")}
    >
      <Globe className="size-3.5 shrink-0" aria-hidden />
      <div className="flex overflow-hidden rounded-md border border-border">
        {LANGS.map((lang, idx) => {
          const active = current === lang.code;
          return (
            <button
              key={lang.code}
              type="button"
              aria-pressed={active}
              onClick={() => void i18n.changeLanguage(lang.code)}
              className={cn(
                "px-2 py-1 text-[11px] font-medium leading-none transition-colors",
                idx > 0 ? "border-l border-border" : "",
                active ? "bg-secondary text-foreground" : "bg-card hover:bg-secondary/60",
              )}
            >
              {lang.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
