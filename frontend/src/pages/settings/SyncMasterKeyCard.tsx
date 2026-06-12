// frontend/src/pages/settings/SyncMasterKeyCard.tsx
//
// Out-of-band master-key transfer (spec 010). Export this machine's key to a
// local file to carry to another machine, or import a key brought from one.
// The key never travels through the sync repo.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useExportMasterKey, useImportMasterKey } from "@/lib/hooks/useSync";

export function SyncMasterKeyCard() {
  const { t } = useTranslation();
  const [keyPath, setKeyPath] = useState("");
  const importKey = useImportMasterKey();
  const exportKey = useExportMasterKey();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.sync.masterKey")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-foreground/70">{t("settings.sync.masterKeyHint")}</p>
        <div className="space-y-2">
          <Label htmlFor="sync-key-path">{t("settings.sync.keyPath")}</Label>
          <Input
            id="sync-key-path"
            value={keyPath}
            placeholder="/path/to/coffer-master.key"
            onChange={(e) => setKeyPath(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() => exportKey.mutate(keyPath)}
            disabled={!keyPath || exportKey.isPending}
          >
            {t("settings.sync.exportKey")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => importKey.mutate(keyPath)}
            disabled={!keyPath || importKey.isPending}
          >
            {t("settings.sync.importKey")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
