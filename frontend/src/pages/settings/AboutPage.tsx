// frontend/src/pages/settings/AboutPage.tsx
//
// Settings → About (design 6.2.13): what this Coffer is. A head line with the
// logo, the running version and, beside it, "Copy diagnostics for a bug
// report" (spec web-ui "Keep daemon shutdown on the command line": version,
// channel, host, daemon state and port and the enabled features, never a token
// or a secret); the desktop shell's update check (`UpdatesSection`, its own
// requirement); and the details — version (with the commit a release was built
// from), license, documentation, source and the data folder. The version comes from
// /daemon/status so it names the build that is actually running. No release
// channel is shown; it stays in the diagnostics.
import { useTranslation } from "react-i18next";

import { CofferMark } from "@/components/brand/CofferMark";
import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { useDaemonFooterState } from "@/components/shell/useDaemonFooterState";
import { useToast } from "@/components/ui/toast";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { inDesktopShell } from "@/lib/tauri";
import { diagnosticsText } from "./aboutDiagnostics";
import { UpdatesSection } from "./UpdatesSection";

/** The published docs site (docs-site/), per interface language: Chinese lives under /zh/. */
const DOCS_URL = {
  en: "https://wyx-sg.github.io/Coffer/",
  zh: "https://wyx-sg.github.io/Coffer/zh/",
} as const;
const SOURCE_URL = "https://github.com/wyx-sg/Coffer";
const EMPTY = "—";

export function AboutPage() {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { data: status } = useDaemonStatus();
  const state = useDaemonFooterState();

  const copyDiagnostics = async () => {
    const text = diagnosticsText({
      status,
      state,
      host: inDesktopShell() ? "desktop app" : "browser",
      platform: typeof navigator !== "undefined" ? navigator.platform : "",
    });
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("settings.about.diagnosticsCopied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  const version = status?.version ?? EMPTY;
  const build = status?.commit
    ? t("settings.about.versionWithCommit", { version, commit: status.commit })
    : version;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3.5" data-testid="settings-about-head">
        <CofferMark size={44} />
        <div className="flex flex-col gap-0.5">
          <h3 className="m-0 text-xl font-bold tracking-tight text-text">Coffer</h3>
          <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-text-muted">
            <span>
              {status
                ? t("settings.about.versionLine", { version })
                : t("settings.about.versionLineLoading")}
            </span>
            <button
              type="button"
              onClick={() => void copyDiagnostics()}
              className="text-xs font-label text-accent underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            >
              {t("settings.about.copyDiagnostics")}
            </button>
          </p>
        </div>
      </div>

      <UpdatesSection />

      <SettingsSection title={t("settings.about.details")}>
        <SettingRow label={t("settings.about.fields.version")}>
          <span className="font-mono text-xs">{build}</span>
        </SettingRow>
        <SettingRow label={t("settings.about.fields.license")}>
          <span className="text-sm">MIT</span>
        </SettingRow>
        <SettingRow label={t("settings.about.fields.documentation")}>
          <a
            href={DOCS_URL[i18n.language?.startsWith("zh") ? "zh" : "en"]}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-accent hover:underline"
          >
            {t("settings.about.documentationLink")}
          </a>
        </SettingRow>
        <SettingRow label={t("settings.about.fields.source")}>
          <a
            href={SOURCE_URL}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-accent hover:underline"
          >
            github.com/wyx-sg/Coffer
          </a>
        </SettingRow>
        <SettingRow label={t("settings.about.fields.dataFolder")}>
          <span className="font-mono text-xs" data-visual-volatile>
            {status?.data_dir ?? EMPTY}
          </span>
        </SettingRow>
      </SettingsSection>
    </div>
  );
}
