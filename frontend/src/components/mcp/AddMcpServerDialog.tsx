// frontend/src/components/mcp/AddMcpServerDialog.tsx
// The Add server dialog (design 4.1; spec web-ui "Add MCP servers by pasting
// them into one box"). Controlled: the page renders the Add server button and mounts
// this. Steps: the paste box → the prefilled form (one server) or the review
// (several). It adds MCP servers only; importing the agents' own entries is done
// on each agent's MCP servers tab, not here.
//
// The one-server form tests the unsaved config before Add server. Adding registers each server, then writes its secrets, then its
// reach (importMcpServers.ts). One server added → its page, where it is tested once;
// several → stay open, test each in the background, and a batch that only partly
// went in stays on the review (board 4.1.26). A secret that goes to a new
// place and waits for approval is said before the dialog lets go (board 4.1.29).
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useAgents } from "@/lib/hooks/useAgents";
import { useImportMcpServers, useTestAddedServers } from "@/lib/hooks/useMcpServerMutations";
import { useResources } from "@/lib/hooks/useResources";
import type { ParsedServer } from "@/lib/mcp/pasteParse";
import { ApprovalStep, type AddedServer } from "./add/ApprovalStep";
import { addedList, reachPhrase } from "./add/addedSummary";
import { headingOf } from "./add/addHeading";
import { PasteStep } from "./add/PasteStep";
import { ReviewStep } from "./add/ReviewStep";
import { ServerForm } from "./add/ServerForm";
import type { FailedServer, NewServer, ReachIntent } from "@/lib/mcp/importMcpServers";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Step =
  | { kind: "paste" }
  | { kind: "form"; server: ParsedServer; seq: number }
  | { kind: "review"; servers: ParsedServer[]; seq: number }
  | { kind: "approval"; added: AddedServer[]; then: { added: Added; reach: ReachIntent } | null };

interface Added {
  name: string;
  uid: string;
}

const emptyServer = (transportType: "stdio" | "http"): ParsedServer => ({
  name: "",
  transportType,
  command: "",
  args: [],
  url: "",
  env: [],
});

export function AddMcpServerDialog({ open, onOpenChange }: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState<Step>({ kind: "paste" });
  const [text, setText] = useState("");
  const [failures, setFailures] = useState<FailedServer[]>([]);
  // What this dialog session already registered (name → uid), so a retry after
  // a partial failure re-attempts only the failures.
  const createdRef = useRef<Map<string, string>>(new Map());
  const seq = useRef(0);
  const add = useImportMcpServers();
  const testAdded = useTestAddedServers();
  const { data: servers } = useResources("mcp_server");
  const { data: agents } = useAgents();
  const taken = new Set((servers ?? []).map((s) => s.name));

  // The page opens the dialog by its `open` prop (Radix reports only closes),
  // so a fresh session starts on the paste box whenever it becomes open.
  useEffect(() => {
    if (!open) return;
    setStep({ kind: "paste" });
    setText("");
    setFailures([]);
    createdRef.current = new Map();
  }, [open]);
  const setOpen = (next: boolean) => onOpenChange(next);

  /** One server added: close, open its page, test it once and toast the result. */
  const finishOne = (added: Added, reach: ReachIntent) => {
    onOpenChange(false);
    navigate(`/mcp-servers/${encodeURIComponent(added.name)}`);
    void testAdded([added.uid]).then(([r]) => {
      if (r.status === "fulfilled" && r.value.ok) {
        const tools = r.value.tool_count ?? 0;
        toast.success(t("mcp.add.toastAdded", { name: added.name }), {
          description:
            reach.mode === "disabled"
              ? t("mcp.add.toastTestedOff", { count: tools })
              : t("mcp.add.toastTested", {
                  count: tools,
                  reach: reachPhrase(t, reach, agents),
                }),
        });
      } else {
        const error =
          r.status === "fulfilled"
            ? (r.value.error_message ?? "")
            : String(r.reason?.message ?? "");
        toast.error(t("mcp.add.toastFailing", { name: added.name, error }));
      }
    });
  };

  const submit = (batch: NewServer[], reach: ReachIntent, single: boolean) => {
    const before = new Set(createdRef.current.keys());
    add.mutate(
      { servers: batch, created: createdRef.current, reach },
      {
        onSuccess: (report) => {
          setFailures(report.failed);
          const fresh = report.created.filter((c) => !before.has(c.name));
          const approval = () =>
            setStep({
              kind: "approval",
              added: addedList(t, batch, report, reach, agents),
              then: single && report.created[0] ? { added: report.created[0], reach } : null,
            });
          if (single) {
            const one = report.created[0];
            if (!one) return;
            if (report.awaitingApproval.length > 0) approval();
            else finishOne(one, reach);
            return;
          }
          void testAdded(fresh.map((c) => c.uid));
          // Some were refused: stay on the review — the added rows say Added, the
          // refused ones say why — instead of a toast that would vanish.
          if (report.failed.length > 0) return;
          toast.success(t("mcp.add.toastAddedMany", { count: report.created.length }));
          if (report.awaitingApproval.length > 0) approval();
          else onOpenChange(false);
        },
      },
    );
  };

  const openServers = (found: ParsedServer[]) => {
    seq.current += 1;
    setFailures([]);
    if (found.length === 1) setStep({ kind: "form", server: found[0], seq: seq.current });
    else setStep({ kind: "review", servers: found, seq: seq.current });
  };

  const heading = headingOf(t, i18n.language, step, createdRef.current, failures);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[90vh] max-w-[640px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{heading.title}</DialogTitle>
          <DialogDescription>{heading.sub}</DialogDescription>
        </DialogHeader>
        {step.kind === "paste" ? (
          <PasteStep
            text={text}
            onTextChange={setText}
            onServers={openServers}
            onChooseType={(type) => openServers([emptyServer(type)])}
            onCancel={() => onOpenChange(false)}
          />
        ) : null}
        {step.kind === "form" ? (
          <ServerForm
            key={step.seq}
            initial={step.server}
            taken={taken}
            pending={add.isPending}
            failure={failures[0] ?? null}
            onChangeType={() => setStep({ kind: "paste" })}
            onCancel={() => onOpenChange(false)}
            onSubmit={(server, reach) => submit([server], reach, true)}
          />
        ) : null}
        {step.kind === "review" ? (
          <ReviewStep
            key={step.seq}
            initial={step.servers}
            taken={taken}
            added={new Set(createdRef.current.keys())}
            failures={failures}
            pending={add.isPending}
            onBack={() => setStep({ kind: "paste" })}
            onClose={() => onOpenChange(false)}
            onSubmit={(batch, reach) => submit(batch, reach, false)}
          />
        ) : null}
        {step.kind === "approval" ? (
          <ApprovalStep
            added={step.added}
            onDone={() =>
              step.then ? finishOne(step.then.added, step.then.reach) : onOpenChange(false)
            }
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
