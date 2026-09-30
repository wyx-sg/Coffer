// frontend/src/pages/sync/SyncJoinChoices.tsx
//
// The files a join found different here and on the remote. A join never
// overwrites either side on its own: each file waits, as it is, until a person
// keeps this Mac's version or takes the remote's — one at a time, or all at
// once when they already know which side is right.
import { useTranslation } from "react-i18next";
import { Download, Laptop } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { useChooseJoin, useJoinChoices } from "@/lib/hooks/useSyncStop";
import { formatDateTime } from "@/lib/utils";

type Side = "mine" | "theirs";

export function SyncJoinChoices() {
  const { t } = useTranslation();
  const { data } = useJoinChoices(true);
  const choose = useChooseJoin();
  const files = data?.files ?? [];
  if (files.length === 0) return null;

  const answer = (paths: string[], side: Side) =>
    choose.mutate(paths.map((path) => ({ path, answer: side })));
  const all = files.map((f) => f.path);

  return (
    <Card data-testid="sync-join-choices">
      <CardHeader>
        <CardTitle>{t("sync.joinChoices.title", { count: files.length })}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("sync.joinChoices.body")}</p>
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            variant="outline"
            disabled={choose.isPending}
            onClick={() => answer(all, "mine")}
          >
            {t("sync.joinChoices.keepAllMine")}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={choose.isPending}
            onClick={() => answer(all, "theirs")}
          >
            {t("sync.joinChoices.takeAllTheirs")}
          </Button>
        </div>
        <Table>
          <TableBody>
            {files.map((file) => (
              <TableRow key={file.path} data-testid={`join-choice-${file.path}`}>
                <TableCell className="font-mono text-xs">{file.path}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {file.theirs_time ? formatDateTime(file.theirs_time) : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <TableActionButton
                      icon={Laptop}
                      label={t("sync.joinChoices.keepMine")}
                      disabled={choose.isPending}
                      onClick={() => answer([file.path], "mine")}
                    />
                    <TableActionButton
                      icon={Download}
                      label={t("sync.joinChoices.takeTheirs")}
                      disabled={choose.isPending}
                      onClick={() => answer([file.path], "theirs")}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
