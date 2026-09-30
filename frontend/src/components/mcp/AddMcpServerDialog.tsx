// frontend/src/components/mcp/AddMcpServerDialog.tsx
// The Add server dialog (design 4.1; spec web-ui "Add MCP servers from one
// paste box"). Controlled: the page renders the Add server button and mounts
// this. Steps: the paste box → the prefilled form (one server) or the review
// (several), plus Import from your agents. It adds MCP servers only.
//
// The one-server form tests the unsaved config before Add server. Import from
// your agents opens the change preview of the daemon's import plan instead of
// this dialog. Adding registers each server, then writes its secrets, then its
// reach (importMcpServers.ts). One server added → its page, where it is tested once;
// several → stay, toast, test each in the background. A secret the daemon
// holds for approval (202) is said before the dialog lets go.
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
import { agentTypeLabel } from "@/lib/agents/display";
import { useAgentDirectMcpEntries } from "@/lib/hooks/useAgentDirectMcpEntries";
import { useAgents } from "@/lib/hooks/useAgents";
import { useImportMcpServers, useTestAddedServers } from "@/lib/hooks/useMcpServerMutations";
import { useResources } from "@/lib/hooks/useResources";
import type { ParsedServer } from "@/lib/mcp/pasteParse";
import { ApprovalStep } from "./add/ApprovalStep";
import { ImportFromAgents, toastImport } from "./add/ImportFromAgents";
import { PasteStep } from "./add/PasteStep";
import { ReviewStep } from "./add/ReviewStep";
import { ServerForm } from "./add/ServerForm";
import type { FailedServer, NewServer, ReachIntent } from "./importMcpServers";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Which view the dialog opens on; the paste box by default. */
  initialMode?: "paste" | "importAgents";
}

type Step =
  | { kind: "paste" }
  | { kind: "form"; server: ParsedServer; seq: number }
  | { kind: "review"; servers: ParsedServer[]; seq: number }
  | { kind: "importAgents" }
  | { kind: "approval"; names: string[]; then: { added: Added; reach: ReachIntent } | null };

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

export function AddMcpServerDialog({ open, onOpenChange, initialMode = "paste" }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState<Step>({ kind: initialMode });
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
  const { count: agentEntryCount } = useAgentDirectMcpEntries();
  const taken = new Set((servers ?? []).map((s) => s.name));

  // The page opens the dialog by its `open` prop (Radix reports only closes),
  // so a fresh session starts whenever it becomes open — on the view it was
  // asked for, the paste box or Import from your agents.
  useEffect(() => {
    if (!open) return;
    setStep({ kind: initialMode });
    setText("");
    setFailures([]);
    createdRef.current = new Map();
  }, [open, initialMode]);
  const setOpen = (next: boolean) => onOpenChange(next);

  const reachPhrase = (reach: ReachIntent) => {
    if (reach.mode === "everywhere") return t("mcp.add.reachAll");
    if (reach.mode === "disabled") return t("mcp.add.reachOff");
    const names = reach.agents.map((uid) => {
      const a = agents?.find((x) => x.uid === uid);
      return a ? agentTypeLabel(a.type ?? a.name) : uid;
    });
    return names.length > 0 ? names.join(", ") : t("mcp.add.reachOff");
  };

  /** One server added: close, open its page, test it once and toast the result. */
  const finishOne = (added: Added, reach: ReachIntent) => {
    onOpenChange(false);
    navigate(`/mcp-servers/${encodeURIComponent(added.name)}`);
    void testAdded([added.uid]).then(([r]) => {
      if (r.status === "fulfilled" && r.value.ok) {
        const tools = r.value.tool_count ?? 0;
        toast.success(
          t("mcp.add.toastTested", { name: added.name, count: tools, reach: reachPhrase(reach) }),
        );
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
          if (single) {
            const one = report.created[0];
            if (!one) return;
            if (report.awaitingApproval.length > 0) {
              setStep({
                kind: "approval",
                names: report.awaitingApproval,
                then: { added: one, reach },
              });
            } else finishOne(one, reach);
            return;
          }
          void testAdded(fresh.map((c) => c.uid));
          if (report.failed.length > 0) {
            const first = report.failed[0];
            toast.info(
              t("mcp.add.toastPartial", {
                done: report.created.length,
                total: report.created.length + report.failed.length,
                names: report.failed.map((f) => f.name).join(", "),
                reason: first.message,
              }),
            );
            return;
          }
          toast.success(t("mcp.add.toastAddedMany", { count: report.created.length }));
          if (report.awaitingApproval.length > 0) {
            setStep({ kind: "approval", names: report.awaitingApproval, then: null });
          } else onOpenChange(false);
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

  const heading =
    step.kind === "review"
      ? { title: t("mcp.add.reviewTitle"), sub: t("mcp.add.reviewSub") }
      : step.kind === "approval"
        ? { title: t("mcp.add.approvalTitle"), sub: t("mcp.add.subtitle") }
        : { title: t("mcp.add.dialogTitle"), sub: t("mcp.add.subtitle") };

  if (step.kind === "importAgents") {
    return (
      <ImportFromAgents
        open={open}
        onOpenChange={setOpen}
        onDone={(result) => {
          toastImport(toast, t, result);
          onOpenChange(false);
        }}
      />
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        className={`max-h-[90vh] overflow-y-auto ${step.kind === "review" ? "max-w-[700px]" : "max-w-[660px]"}`}
      >
        <DialogHeader>
          <DialogTitle>{heading.title}</DialogTitle>
          <DialogDescription>{heading.sub}</DialogDescription>
        </DialogHeader>
        {step.kind === "paste" ? (
          <PasteStep
            text={text}
            onTextChange={setText}
            agentEntryCount={agentEntryCount}
            onServers={openServers}
            onChooseType={(type) => openServers([emptyServer(type)])}
            onImportAgents={() => setStep({ kind: "importAgents" })}
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
            onBack={() => setStep({ kind: "paste" })}
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
            onSubmit={(batch, reach) => submit(batch, reach, false)}
          />
        ) : null}
        {step.kind === "approval" ? (
          <ApprovalStep
            names={step.names}
            onDone={() =>
              step.then ? finishOne(step.then.added, step.then.reach) : onOpenChange(false)
            }
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
