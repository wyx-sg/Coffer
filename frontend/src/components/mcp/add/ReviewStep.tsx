// frontend/src/components/mcp/add/ReviewStep.tsx — the review of several pasted
// servers (board Mcp-Import-Review; spec web-ui "Add MCP servers from one paste
// box"). Nothing is saved until Add: every card's name is the one it will keep
// and can be corrected here, a name over 24 characters (or taken, or repeated
// in the batch) holds the Add button, and one reach choice covers the batch.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import type { ParsedServer } from "@/lib/mcp/pasteParse";
import type { FailedServer, NewServer, ReachIntent } from "../importMcpServers";
import { missingSecretValues } from "../importMcpServers";
import { nameSendable } from "./nameProblem";
import { ReachPick } from "./ReachPick";
import { ReviewCard } from "./ReviewCard";

interface Props {
  initial: ParsedServer[];
  /** Names already registered. */
  taken: ReadonlySet<string>;
  /** Names an earlier attempt of this dialog already registered. */
  added: ReadonlySet<string>;
  /** Why servers of the last attempt were not added. */
  failures: FailedServer[];
  pending: boolean;
  onBack: () => void;
  onSubmit: (servers: NewServer[], reach: ReachIntent) => void;
}

interface Row {
  server: NewServer;
  include: boolean;
}

export function ReviewStep({ initial, taken, added, failures, pending, onBack, onSubmit }: Props) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Row[]>(() =>
    initial.map((server) => ({ server, include: true })),
  );
  const [reach, setReach] = useState<ReachIntent>({ mode: "everywhere" });
  const patch = (i: number, next: Partial<Row>) =>
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...next } : r)));

  const failureOf = (name: string) => failures.find((f) => f.name === name);
  // A card's name must differ from every registered name, from any the
  // daemon just refused as taken, and from the other included cards.
  const takenFor = (i: number): Set<string> => {
    const out = new Set(taken);
    for (const f of failures) if (f.nameTaken) out.add(f.name);
    rows.forEach((r, j) => {
      if (j !== i && r.include) out.add(r.server.name);
    });
    return out;
  };
  const pendingRows = rows.filter((r) => r.include && !added.has(r.server.name));
  const blocked = rows.some(
    (r, i) =>
      r.include &&
      !added.has(r.server.name) &&
      (!nameSendable(r.server.name, takenFor(i)) || missingSecretValues(r.server).length > 0),
  );
  const included = rows.filter((r) => r.include).map((r) => r.server);

  return (
    <>
      <p className="text-xs font-label text-text-muted">
        {t("mcp.add.found", { count: rows.length })}
      </p>
      <div className="max-h-[50vh] space-y-2.5 overflow-y-auto pr-1">
        {rows.map((row, i) => {
          const failure = failureOf(row.server.name);
          return (
            <ReviewCard
              key={i}
              index={i}
              server={row.server}
              include={row.include}
              added={added.has(row.server.name)}
              taken={takenFor(i)}
              error={failure && !failure.nameTaken ? failure.message : undefined}
              onInclude={(include) => patch(i, { include })}
              onChange={(server) => patch(i, { server })}
            />
          );
        })}
      </div>
      <ReachPick value={reach} onChange={setReach} busy={pending} />
      <p className="text-xs text-text-muted">{t("mcp.add.reviewFootnote")}</p>
      <DialogFooter>
        <Button variant="ghost" className="sm:mr-auto" onClick={onBack} disabled={pending}>
          {t("mcp.add.back")}
        </Button>
        <Button
          disabled={pending || blocked || pendingRows.length === 0}
          onClick={() => onSubmit(included, reach)}
        >
          {pending ? t("mcp.add.adding") : t("mcp.add.addN", { count: pendingRows.length })}
        </Button>
      </DialogFooter>
    </>
  );
}
