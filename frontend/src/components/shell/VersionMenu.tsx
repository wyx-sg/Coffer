// src/components/shell/VersionMenu.tsx — the menu the sidebar footer opens: version, daemon, theme, language, docs, updates.
//
// Boards 1.2.06 and 1.2.23: the footer row ("● Daemon running … v1.0.0", the
// dot alone on the rail) opens a 280-wide menu above it. Its head names the
// version and where the daemon answers — that line opens Settings › Daemon —
// then Theme (Light / Dark / System, applied at once), Language (each locale
// named in its own language), Documentation and Check for updates. Theme and
// language live here and in Settings › General; Settings itself is only the
// sidebar row and ⌘,.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { BookOpen, Check, ChevronRight, Download, Languages, SunMoon } from "lucide-react";

import { StatusDot } from "@/components/status/StatusDot";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useShellUpdates } from "@/lib/hooks/useShellUpdates";
import { useOpenSettings } from "@/lib/settingsModal";
import { useSetThemePreference, useThemePreference, type ThemePreference } from "@/lib/theme";
import { cn } from "@/lib/utils";
import type { DaemonFooterState } from "./useDaemonFooterState";

/** The published docs site (docs-site/). */
const DOCS_URL = "https://wyx-sg.github.io/Coffer/";
/** The daemon only ever listens on loopback. */
const DAEMON_HOST = "127.0.0.1";

const THEMES: readonly ThemePreference[] = ["light", "dark", "system"];
const LOCALES = [
  { code: "en", own: "English", langTag: "en" },
  { code: "zh", own: "简体中文", langTag: "zh-Hans" },
] as const;

const ITEM =
  "flex h-control-md w-full items-center gap-[9px] rounded-item px-2 text-left text-sm text-text transition-colors duration-fast hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none";

function Separator() {
  return <div role="separator" className="mx-0 my-1 h-px bg-border-subtle" />;
}

function ItemIcon({ children }: { children: ReactNode }) {
  return <span className="inline-flex w-3.5 shrink-0 text-text-muted">{children}</span>;
}

interface Props {
  state: DaemonFooterState;
  /** The dot the trigger and the head show for the state. */
  tone: "ok" | "warn" | "err" | "off";
  /** The state in words, for the head when the daemon is not running. */
  stateLabel: string;
  collapsed: boolean;
  /** The footer row (or the rail's dot) that opens the menu. */
  trigger: JSX.Element;
  /** A tooltip over the trigger — the rail's dot has no words of its own. */
  tooltip?: string;
}

export function VersionMenu({ state, tone, stateLabel, collapsed, trigger, tooltip }: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [languagesOpen, setLanguagesOpen] = useState(true);
  const openSettings = useOpenSettings();
  const theme = useThemePreference();
  const setTheme = useSetThemePreference();
  const updates = useShellUpdates();
  const current = i18n.language.startsWith("zh") ? "zh" : "en";
  const version = state.kind === "connecting" ? null : state.version;

  const go = (run: () => void) => () => {
    setOpen(false);
    run();
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      {tooltip ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>{trigger}</PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="right">{tooltip}</TooltipContent>
        </Tooltip>
      ) : (
        <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      )}
      <PopoverContent
        side={collapsed ? "right" : "top"}
        align={collapsed ? "end" : "start"}
        aria-label={t("nav.versionMenu.label")}
        className="w-[280px] p-1 text-sm text-text"
        data-testid="version-menu"
      >
        <button
          type="button"
          onClick={go(() => openSettings("daemon"))}
          className="flex w-full flex-col gap-0.5 rounded-item px-2 pb-2.5 pt-2 text-left hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none"
        >
          <span className="text-sm font-semibold text-text">
            {version ? t("nav.versionMenu.title", { version }) : "Coffer"}
          </span>
          <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
            <StatusDot tone={tone} size={6} />
            {state.kind === "running" ? (
              <>
                {t("nav.versionMenu.daemonOn")}
                <span className="font-mono text-2xs">{`${DAEMON_HOST}:${state.port}`}</span>
              </>
            ) : (
              stateLabel
            )}
          </span>
        </button>
        <Separator />
        <div className="flex items-center gap-[9px] px-2 pb-1.5 pt-1">
          <ItemIcon>
            <SunMoon className="size-3.5" aria-hidden />
          </ItemIcon>
          <span className="text-sm">{t("nav.versionMenu.theme")}</span>
          <Segmented<ThemePreference>
            className="ml-auto"
            label={t("nav.versionMenu.theme")}
            value={theme}
            onChange={setTheme}
            options={THEMES.map((p) => ({ value: p, label: t(`nav.versionMenu.themes.${p}`) }))}
          />
        </div>
        <button
          type="button"
          className={ITEM}
          aria-expanded={languagesOpen}
          onClick={() => setLanguagesOpen((v) => !v)}
        >
          <ItemIcon>
            <Languages className="size-3.5" aria-hidden />
          </ItemIcon>
          {t("nav.language")}
          <span className="ml-auto inline-flex items-center gap-1 text-2xs text-text-muted">
            {LOCALES.find((l) => l.code === current)?.own}
            <ChevronRight
              className={cn("size-3 transition-transform", languagesOpen && "rotate-90")}
              aria-hidden
            />
          </span>
        </button>
        {languagesOpen ? (
          <div
            role="radiogroup"
            aria-label={t("nav.language")}
            className="mb-1 ml-[23px] mt-0.5 flex flex-col gap-px border-l border-border-subtle pl-2"
          >
            {LOCALES.map((locale) => {
              const selected = locale.code === current;
              return (
                <button
                  key={locale.code}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  lang={locale.langTag}
                  onClick={() => void i18n.changeLanguage(locale.code)}
                  className={cn(ITEM, "gap-2", selected && "bg-surface-hover")}
                >
                  {locale.own}
                  <span className="ml-auto inline-flex text-2xs text-text-muted">
                    {selected ? (
                      <Check className="size-3.5 text-accent-text" aria-hidden />
                    ) : (
                      t(`nav.versionMenu.localeIn.${locale.code}`)
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}
        <Separator />
        <a
          href={DOCS_URL}
          target="_blank"
          rel="noreferrer"
          className={ITEM}
          onClick={() => setOpen(false)}
        >
          <ItemIcon>
            <BookOpen className="size-3.5" aria-hidden />
          </ItemIcon>
          {t("nav.versionMenu.documentation")}
        </a>
        <button
          type="button"
          className={ITEM}
          onClick={go(() => {
            // The desktop shell checks now and Settings › About shows the
            // result; a browser cannot replace the app, and About says so.
            if (updates.inShell) void updates.check();
            openSettings("about");
          })}
        >
          <ItemIcon>
            <Download className="size-3.5" aria-hidden />
          </ItemIcon>
          {t("nav.versionMenu.checkUpdates")}
        </button>
      </PopoverContent>
    </Popover>
  );
}
