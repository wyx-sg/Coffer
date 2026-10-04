// frontend/src/components/mcp/add/ReviewStep.tsx — the review of several pasted
// servers (board Mcp-Import-Review; spec web-ui "Add MCP servers from one paste
// box"). Nothing is saved until Add: every card's name is the one it will keep
// and can be corrected here, a name over 24 characters (or taken, or repeated
// in the batch) holds the Add button, and one reach choice covers the batch.
// A batch that only partly went in stays open (board Mcp-Add-ReviewPartial): the
// added rows say Added, a refused one says why and its name can be changed, and
// Add N server(s) tries only those; Close ends it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import type { ParsedServer } from "@/lib/mcp/pasteParse";
import type { FailedServer, NewServer, ReachIntent } from "@/lib/mcp/importMcpServers";
import { missingSecretValues } from "@/lib/mcp/importMcpServers";
import { askedKeysOf, keptRows, promoteAsked, rowsFromParsed } from "@/lib/mcp/serverRows";
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
  /** Back to the paste box; once some servers are added it is Close instead. */
  onBack: () => void;
  onClose: () => void;
  onSubmit: (servers: NewServer[], reach: ReachIntent) => void;
}

interface Row {
  server: NewServer;
  include: boolean;
  /** Keys that arrived flagged secret without a value. */
  asked: Set<string>;
}

export function ReviewStep({
  initial,
  taken,
  added,
  failures,
  pending,
  onBack,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Row[]>(() => {
    return initial.map((server) => ({
      server: { ...server, env: rowsFromParsed(server.env, true) },
      include: true,
      asked: askedKeysOf(server.env),
    }));
  });
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
  // An asked key stays asked for until its value is typed in.
  const unfilled = (r: Row) =>
    r.server.env.some(
      (e) => r.asked.has(e.key.trim()) && e.value.kind === "plain" && e.value.value === "",
    );
  const pendingRows = rows.filter((r) => r.include && !added.has(r.server.name));
  const blocked = rows.some(
    (r, i) =>
      r.include &&
      !added.has(r.server.name) &&
      (!nameSendable(r.server.name, takenFor(i)) ||
        missingSecretValues(r.server).length > 0 ||
        unfilled(r)),
  );
  // What was flagged secret and typed in becomes a new secret, never plain text.
  const included = rows
    .filter((r) => r.include)
    .map((r) => ({
      ...r.server,
      env: promoteAsked(keptRows(r.server.env), r.asked),
    }));

  return (
    <>
      <p className="text-sm font-label text-text">
        {added.size > 0
          ? t("mcp.add.addedOf", { done: added.size, total: rows.length })
          : t("mcp.add.found", { count: rows.length })}
      </p>
      <div className="max-h-[50vh] overflow-y-auto border-b border-border-subtle pr-1">
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
              asked={row.asked}
              onInclude={(include) => patch(i, { include })}
              onChange={(server) => patch(i, { server })}
            />
          );
        })}
      </div>
      <ReachPick value={reach} onChange={setReach} busy={pending} scope="batch" />
      <p className="text-xs text-text-muted">{t("mcp.add.reviewFootnote")}</p>
      <DialogFooter>
        <Button variant="ghost" onClick={added.size > 0 ? onClose : onBack} disabled={pending}>
          {added.size > 0 ? t("common.close") : t("mcp.add.back")}
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
