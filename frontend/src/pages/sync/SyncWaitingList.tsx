// frontend/src/pages/sync/SyncWaitingList.tsx
//
// What this machine has committed that the remote does not have yet — every
// change the next round pushes, and who made it. The writer matters: a file a
// person edited on disk, one an agent wrote, and one Coffer's own upkeep
// rewrote are different things to find in the list when something looks wrong.
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { WaitingCommit } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";

/** The daemon's writers, in the four words a person reads them as. */
const WRITER: Record<string, string> = {
  user: "you",
  daemon: "coffer",
  curation: "coffer",
  sync: "coffer",
  disk: "disk",
  agent: "agent",
};

const COLUMNS = ["file", "change", "writer", "time"] as const;

export function SyncWaitingList({ waiting }: { waiting: WaitingCommit[] }) {
  const { t } = useTranslation();
  const rows = waiting.flatMap((commit) =>
    commit.changes.map((change) => ({ commit, change, key: `${commit.version}:${change.path}` })),
  );
  if (rows.length === 0) return null;

  return (
    <Card data-testid="sync-waiting">
      <CardHeader>
        <CardTitle>{t("sync.waiting.title", { count: rows.length })}</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              {COLUMNS.map((c) => (
                <TableHead key={c}>{t(`sync.waiting.columns.${c}`)}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map(({ commit, change, key }) => (
              <TableRow key={key}>
                <TableCell className="font-mono text-xs">{change.path}</TableCell>
                <TableCell className="text-xs">{t(`sync.change.${change.status}`)}</TableCell>
                <TableCell className="text-xs">
                  {t(`sync.waiting.writer.${WRITER[commit.writer] ?? "coffer"}`)}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatDateTime(commit.time)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
