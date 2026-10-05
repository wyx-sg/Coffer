// src/components/agents/hooks/HookDetailsDialog.tsx — one of the agent's own hooks, read-only (board 2.1.63).
//
// Wide (640). The command in full in a pre, then Event (with its one-line
// explanation), Matcher, Type, Timeout, File and the entry's JSON position, so
// the hook can be found in its file. Nothing here writes: a hook is changed in
// its own file, which "Open in editor" opens in the person's editor.
import { useTranslation } from "react-i18next";
import { Check, Copy, ExternalLink } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { hookEntryPath } from "@/lib/agents/hookRows";
import type { NativeHook } from "@/lib/api/agents";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useCopyText } from "@/lib/hooks/useCopyText";

interface Props {
  hook: NativeHook | null;
  agentType: string;
  onClose: () => void;
}

// A hook event whose one-line explanation is written (`agents.hooks.eventHelp.<event>`).
const EXPLAINED = new Set([
  "SessionStart",
  "UserPromptSubmit",
  "PreToolUse",
  "PostToolUse",
  "Stop",
  "Notification",
  "SubagentStop",
  "PreCompact",
  "SessionEnd",
]);

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_minmax(0,1fr)] items-baseline gap-4 border-t border-border-subtle py-2.5 first:border-t-0">
      <dt className="text-sm font-medium text-text">{label}</dt>
      <dd className="min-w-0 text-sm text-text-muted">{children}</dd>
    </div>
  );
}

export function HookDetailsDialog({ hook, agentType, onClose }: Props) {
  const { t } = useTranslation();
  const { copied, copy } = useCopyText();
  const [open] = useFileActionItems(hook?.path ?? "");
  return (
    <Dialog open={hook !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[640px]">
        {hook ? (
          <>
            <DialogHeader>
              <DialogTitle>{t("agents.hooks.details.title", { event: hook.event })}</DialogTitle>
              <DialogDescription>
                {t("agents.hooks.details.description", { agent: agentTypeLabel(agentType) })}
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium text-text">
                {t("agents.hooks.details.command")}
              </span>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md bg-code px-3 py-2.5 font-mono text-xs text-text">
                {hook.command}
              </pre>
            </div>
            <dl className="flex flex-col border-t border-border-subtle">
              <Row label={t("agents.hooks.details.event")}>
                <span className="font-mono text-xs text-text">{hook.event}</span>
                {EXPLAINED.has(hook.event) ? (
                  <span className="ml-2 text-xs">{t(`agents.hooks.eventHelp.${hook.event}`)}</span>
                ) : null}
              </Row>
              <Row label={t("agents.hooks.details.matcher")}>
                {hook.matcher ? (
                  <span className="font-mono text-xs text-text">{hook.matcher}</span>
                ) : (
                  t("agents.hooks.details.anyTool")
                )}
              </Row>
              <Row label={t("agents.hooks.details.type")}>
                {hook.type === "command" ? t("agents.hooks.details.shellCommand") : hook.type}
              </Row>
              <Row label={t("agents.hooks.details.timeout")}>
                {hook.timeout !== null
                  ? t("agents.hooks.details.seconds", { count: hook.timeout })
                  : t("agents.hooks.details.timeoutDefault")}
              </Row>
              <Row label={t("agents.hooks.details.file")}>
                <span className="break-all font-mono text-xs text-text">
                  {abbreviateHomePath(hook.path)}
                </span>
              </Row>
              <Row label={t("agents.hooks.details.entry")}>
                <span className="break-all font-mono text-xs">{hookEntryPath(hook)}</span>
              </Row>
            </dl>
            <DialogFooter className="sm:justify-between">
              <Button variant="ghost" onClick={() => copy(hook.command)}>
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}{" "}
                {copied ? t("common.copied") : t("agents.hooks.details.copy")}
              </Button>
              <span className="flex flex-col-reverse gap-2 sm:flex-row">
                <Button variant="outline" onClick={open.onClick}>
                  <ExternalLink aria-hidden /> {open.label}
                </Button>
                <Button variant="ghost" onClick={onClose}>
                  {t("common.close")}
                </Button>
              </span>
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
