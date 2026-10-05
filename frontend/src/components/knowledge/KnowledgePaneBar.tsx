// frontend/src/components/knowledge/KnowledgePaneBar.tsx
//
// The 48px bar over every Knowledge pane view (boards 5.1.01, 5.1.09, 5.1.10,
// 5.1.13): where you are — the collection, its folders and the open file in
// the mono face — then its actions pushed right. One component so a document, an
// item, a collection and a pass all say where they are the same way. The
// leading segments give way first (ellipsis) when the path is long, and the
// tooltip names the whole path only then.
import { useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface Crumb {
  label: string;
  /** Where the crumb leads; the last crumb is where you are and leads nowhere. */
  to?: string;
  /** A file-system name (collection, folder, file) — drawn in the mono face. */
  mono?: boolean;
}

interface Props {
  crumbs: Crumb[];
  actions?: ReactNode;
}

export function KnowledgePaneBar({ crumbs, actions }: Props) {
  const { t } = useTranslation();
  const navRef = useRef<HTMLElement>(null);
  const [tipOpen, setTipOpen] = useState(false);
  // The full path is only worth a tooltip when some segment is cut off.
  const clipped = () =>
    Array.from(navRef.current?.querySelectorAll("a, span[data-crumb]") ?? []).some(
      (el) => el.scrollWidth > el.clientWidth,
    );
  return (
    <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-border-subtle px-6">
      <TooltipProvider>
        <Tooltip open={tipOpen} onOpenChange={(next) => setTipOpen(next && clipped())}>
          <TooltipTrigger asChild>
            <nav
              ref={navRef}
              aria-label={t("knowledge.document.where")}
              className="flex min-w-0 items-center gap-1 overflow-hidden whitespace-nowrap"
            >
              {crumbs.map((c, i) => {
                const last = i === crumbs.length - 1;
                const cls = cn(
                  "block min-w-0 truncate",
                  last && "shrink-0",
                  c.mono ? "font-mono text-xs" : "text-sm",
                  last ? "text-text" : "text-text-muted hover:text-text",
                );
                return (
                  <span
                    key={`${i}-${c.label}`}
                    className={cn("flex items-center gap-1", last ? "shrink-0" : "min-w-0")}
                  >
                    {i > 0 ? (
                      <ChevronRight className="size-3 shrink-0 text-text-subtle" aria-hidden />
                    ) : null}
                    {c.to && !last ? (
                      <Link to={c.to} className={cls}>
                        {c.label}
                      </Link>
                    ) : (
                      <span
                        data-crumb=""
                        className={cls}
                        aria-current={last ? "location" : undefined}
                      >
                        {c.label}
                      </span>
                    )}
                  </span>
                );
              })}
            </nav>
          </TooltipTrigger>
          <TooltipContent className="max-w-[420px] break-all font-mono">
            {crumbs.map((c) => c.label).join("/")}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      {actions ? (
        <span className="ml-auto flex shrink-0 items-center gap-1.5">{actions}</span>
      ) : null}
    </div>
  );
}
