// frontend/src/components/mcp/add/addHeading.ts — the Add dialog's title and the
// line under it, which follow the step (and, on a review that only partly went
// in, say what was added and what to rename; boards 4.1.26 / 4.1.29).
import type { TFunction } from "i18next";

import type { FailedServer } from "@/lib/mcp/importMcpServers";
import type { AddedServer } from "./ApprovalStep";

export type HeadingStep =
  | { kind: "approval"; added: AddedServer[] }
  | { kind: "review" }
  | { kind: "paste" | "form" | "importAgents" };

export function headingOf(
  t: TFunction,
  lang: string,
  step: HeadingStep,
  created: ReadonlyMap<string, string>,
  failures: FailedServer[],
): { title: string; sub: string } {
  if (step.kind === "approval") {
    const waiting = step.added.filter((s) => s.waiting.length > 0);
    return {
      title: t("mcp.add.approvalTitle"),
      sub: t("mcp.add.approval.sub", {
        count: waiting.length,
        names: waiting.map((s) => s.name).join(", "),
      }),
    };
  }
  if (step.kind === "review") {
    if (created.size > 0 && failures.length > 0) {
      const list = new Intl.ListFormat(lang, { type: "conjunction" });
      const tail = t("mcp.add.renameTail", {
        count: failures.length,
        names: list.format(failures.map((f) => f.name)),
      });
      return {
        title: t("mcp.add.reviewTitle"),
        sub: t("mcp.add.partialSub", { count: created.size, added: list.format([...created.keys()]), tail }),
      };
    }
    return { title: t("mcp.add.reviewTitle"), sub: t("mcp.add.reviewSub") };
  }
  return { title: t("mcp.add.dialogTitle"), sub: t("mcp.add.subtitle") };
}

