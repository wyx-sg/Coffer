// frontend/src/components/mcp/add/PasteStep.tsx — the Add server dialog's first
// step (board Mcp-Add-Picker; spec web-ui "Add MCP servers by pasting them into one box",
// "Explain unreadable pasted input in the dialog").
//
// One box read as the user types (debounced): an mcpServers block or server
// object, Codex TOML, a command line or a URL. The line under it says what was
// found, or why nothing was — with the parse location — and the two type
// buttons open the empty form, so unreadable input always has a way on. This
// step sends no request: it only reads text.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Globe, SquareTerminal } from "lucide-react";

import { StatusDot } from "@/components/status/StatusDot";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { describePaste, parsePaste, type ParsedServer } from "@/lib/mcp/pasteParse";

const DEBOUNCE_MS = 150;

interface Props {
  text: string;
  onTextChange: (text: string) => void;
  onServers: (servers: ParsedServer[]) => void;
  onChooseType: (type: "stdio" | "http") => void;
  onCancel: () => void;
}

function TypeButton(props: {
  icon: React.ReactNode;
  title: string;
  sub: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      className="flex items-start gap-2.5 rounded-lg border border-border bg-surface-raised p-3 text-left transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
    >
      <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
        {props.icon}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{props.title}</span>
        <span className="text-xs text-text-muted">{props.sub}</span>
      </span>
    </button>
  );
}

export function PasteStep({ text, onTextChange, onServers, onChooseType, onCancel }: Props) {
  const { t } = useTranslation();
  const [settled, setSettled] = useState(text);
  useEffect(() => {
    const id = setTimeout(() => setSettled(text), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [text]);
  const result = useMemo(() => parsePaste(settled), [settled]);
  const line = describePaste(result);
  const servers = result.kind === "servers" ? result.servers : [];
  const go = () => onServers(servers);

  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="mcp-paste">{t("mcp.add.pasteLabel")}</Label>
        <Textarea
          id="mcp-paste"
          className="h-28 resize-none font-mono text-xs"
          spellCheck={false}
          value={text}
          aria-invalid={result.kind === "unreadable" || undefined}
          aria-describedby="mcp-paste-result"
          onChange={(e) => onTextChange(e.target.value)}
        />
        <div id="mcp-paste-result" aria-live="polite" className="min-h-4 text-xs">
          {line && result.kind === "servers" ? (
            <p className="flex items-center gap-2 text-text">
              <Check aria-hidden className="size-3.5 shrink-0 text-success" />
              <span>{t(`mcp.paste.${line.key}`, line.params)}</span>
            </p>
          ) : null}
          {line && result.kind === "unreadable" ? (
            <div role="alert" className="space-y-0.5 text-danger">
              <p className="flex items-center gap-2 font-label">
                <StatusDot tone="err" />
                {t("mcp.paste.unreadable")}
              </p>
              <p className="pl-4">{t(`mcp.paste.${line.key}`, line.params)}</p>
            </div>
          ) : null}
        </div>
        <p className="text-xs text-text-muted">{t("mcp.paste.hint")}</p>
      </div>

      <div className="space-y-2">
        <p className="text-2xs font-label text-text-muted">{t("mcp.add.chooseType")}</p>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          <TypeButton
            icon={<SquareTerminal className="size-3.5" />}
            title={t("mcp.add.type.stdio")}
            sub={t("mcp.add.type.stdioSub")}
            onClick={() => onChooseType("stdio")}
          />
          <TypeButton
            icon={<Globe className="size-3.5" />}
            title={t("mcp.add.type.http")}
            sub={t("mcp.add.type.httpSub")}
            onClick={() => onChooseType("http")}
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={servers.length === 0} onClick={go}>
          {servers.length > 1
            ? t("mcp.add.reviewN", { count: servers.length })
            : t("mcp.add.continue")}
        </Button>
      </DialogFooter>
    </>
  );
}
