// frontend/src/pages/settings/AboutPage.tsx
//
// Settings → About: what this Coffer is — version, license and source, and
// nothing else. The version comes from /daemon/status so it names the build
// that is actually running, not a constant baked into the page; the daemon's
// port and start time stay off it, because a user never needs to know Coffer
// runs a background daemon. "Copy diagnostics" puts the same rows on the
// clipboard as plain text, for pasting into a bug report.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";

const SOURCE_URL = "https://github.com/wyx-sg/Coffer";
const EMPTY = "—";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="w-32 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-all">{value}</span>
    </div>
  );
}

export function AboutPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: status } = useDaemonStatus();

  // Label + text value per row: the table renders these, and the clipboard
  // gets the same lines joined — one source, so the two can't drift.
  const rows: { key: string; label: string; text: string }[] = [
    { key: "version", label: t("settings.about.fields.version"), text: status?.version ?? EMPTY },
    { key: "license", label: t("settings.about.fields.license"), text: "MIT" },
    { key: "source", label: t("settings.about.fields.source"), text: SOURCE_URL },
  ];

  const copyDiagnostics = async () => {
    const text = rows.map((r) => `${r.label}: ${r.text}`).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("common.copied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <CardTitle>{t("settings.about.title")}</CardTitle>
          <Button variant="secondary" size="sm" onClick={() => void copyDiagnostics()}>
            <Copy className="mr-1.5 size-3.5" aria-hidden />
            {t("settings.about.copyDiagnostics")}
          </Button>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {rows.map((r) => (
            <Row
              key={r.key}
              label={r.label}
              value={
                r.key === "source" ? (
                  <a
                    href={SOURCE_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    github.com/wyx-sg/Coffer
                  </a>
                ) : (
                  r.text
                )
              }
            />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
