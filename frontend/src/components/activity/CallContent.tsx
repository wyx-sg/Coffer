// src/components/activity/CallContent.tsx — a tool call's recorded content in its drawer (canvas 6.2.03).
//
// Spec web-ui "Filter each Activity tab and expand any row": after the call's
// answer, what it carried — Arguments, Result or Error, and a custom tool's
// Request and Response — each a foldable block with Copy, read when the drawer
// opens (spec mcp-gateway "Record invocations with redacted, bounded content").
// A cut part ends in its cut note; a call recorded while recording was off
// says so and links to the setting.
import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Copy, Info } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LoadError } from "@/components/LoadError";
import { CodeView } from "@/components/preview/CodeView";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import type { CapturedPart } from "@/lib/api/activity";
import { useCallDetail } from "@/lib/hooks/useCallContent";

const PARTS = ["arguments", "result", "error", "request", "response"] as const;
type PartName = (typeof PARTS)[number];

/** The part laid out as JSON when it is whole and parses, as recorded otherwise. */
function partText(part: CapturedPart): { text: string; json: boolean } {
  if (!part.truncated) {
    try {
      return { text: JSON.stringify(JSON.parse(part.text), null, 2), json: true };
    } catch {
      // not JSON — shown as it is
    }
  }
  return { text: part.text, json: false };
}

function PartFold({ name, part }: { name: PartName; part: CapturedPart }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [open, setOpen] = useState(true);
  const Chevron = open ? ChevronDown : ChevronRight;
  const { text, json } = partText(part);
  const label = t(`activity.drawer.content.${name}`);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("common.copied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };
  return (
    <div className="flex flex-col gap-2" data-testid={`call-content-${name}`}>
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex w-fit items-center gap-1.5 text-sm font-semibold text-text"
        >
          <Chevron className="size-3.5 text-text-subtle" aria-hidden />
          {label}
        </button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => void copy()}
          aria-label={t("activity.drawer.content.copy", { part: label })}
        >
          <Copy aria-hidden /> {t("common.copy")}
        </Button>
      </div>
      {open ? (
        <>
          <CodeView
            value={text}
            language={json ? "json" : undefined}
            maxHeight="20rem"
            wrap
            ariaLabel={label}
            className="bg-surface-sunken"
          />
          {part.truncated ? (
            <p className="text-xs text-text-muted">
              {t("activity.drawer.content.cut", {
                size: Math.max(1, Math.round(part.bytes / 1024)),
              })}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function CallContent({ id }: { id: number }) {
  const { t } = useTranslation();
  const detail = useCallDetail(id);
  if (detail.isPending) return <Skeleton className="h-24 w-full" />;
  if (detail.error) return <LoadError error={detail.error} onRetry={() => void detail.refetch()} />;
  const content = detail.data.content;
  if (!content) {
    return (
      <p className="flex items-start gap-1.5 text-xs leading-[1.45] text-text-muted">
        <Info className="mt-px size-3.5 shrink-0 text-text-subtle" aria-hidden />
        <span>
          {t("activity.drawer.content.notRecorded")}{" "}
          <Link to="/settings/data" className="text-accent-text hover:underline">
            {t("activity.drawer.content.setting")}
          </Link>
        </span>
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {PARTS.map((name) => {
        const part = content[name];
        return part ? <PartFold key={name} name={name} part={part} /> : null;
      })}
      <p className="flex items-start gap-1.5 text-xs leading-[1.45] text-text-muted">
        <Info className="mt-px size-3.5 shrink-0 text-text-subtle" aria-hidden />
        {t("activity.drawer.callNote")}
      </p>
    </div>
  );
}
