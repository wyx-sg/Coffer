import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="w-24 text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function AboutPage() {
  const { t } = useTranslation();
  // Version comes from /daemon/status — keeps the UI in sync with the
  // actual running daemon instead of a hardcoded constant.
  const { data: status } = useDaemonStatus();
  const version = status?.version ?? "—";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.about.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label={t("settings.about.fields.name")} value="Coffer" />
          <Row label={t("settings.about.fields.version")} value={version} />
          <Row label={t("settings.about.fields.license")} value="MIT" />
          <Row
            label={t("settings.about.fields.source")}
            value={
              <a
                href="https://github.com/wyx-sg/Coffer"
                target="_blank"
                rel="noreferrer"
                className="text-primary hover:underline"
              >
                github.com/wyx-sg/Coffer
              </a>
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}
