// frontend/src/components/memory/MemoryFactCard.tsx
//
// One fact: title/description/type, plus WHERE it came from (spec memory
// FR-062 / ADR aggregate-agent-memory-never-write-it — "everything here is
// derived ... show its origins") and the developer's own decisions (the four
// overrides minus settle, which lives on the conflict pair in
// MemoryConflictsPanel instead — hide, pin and supersede below).
//
// Origins are fetched lazily on "show origins": a fact's summary (the list
// payload) carries no body/origins, only `GET .../facts/{slug}` does, and a
// partition can hold hundreds of facts, so eagerly fetching every one's
// detail would turn one page load into hundreds of requests.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Pin, PinOff, Eye, EyeOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FactSummaryOut, OverrideOut } from "@/lib/api/memoryTypes";
import { useClearOverride, useMemoryFact, useSetOverride } from "@/lib/hooks/useMemory";

interface Props {
  fact: FactSummaryOut;
  override: OverrideOut | undefined;
  partition: string;
  /** Every other active fact in this partition, for the "mark superseded by"
   *  picker. */
  candidates: FactSummaryOut[];
}

export function MemoryFactCard({ fact, override, partition, candidates }: Props) {
  const { t } = useTranslation();
  const [showOrigins, setShowOrigins] = useState(false);
  const [supersedeTarget, setSupersedeTarget] = useState<string>("");
  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const detail = useMemoryFact(partition, showOrigins ? fact.slug : null);
  const setOverride = useSetOverride();
  const clearOverride = useClearOverride();

  const busy = setOverride.isPending || clearOverride.isPending;
  const settledSupersede = Boolean(override?.superseded_by);

  const toggleHidden = () => {
    if (fact.hidden) clearOverride.mutate({ factKey: fact.key, field: "hidden" });
    else setOverride.mutate({ factKey: fact.key, patch: { hidden: true } });
  };
  const togglePinned = () => {
    if (fact.pinned) clearOverride.mutate({ factKey: fact.key, field: "pinned" });
    else setOverride.mutate({ factKey: fact.key, patch: { pinned: true } });
  };
  const applySupersede = () => {
    if (!supersedeTarget) return;
    setOverride.mutate(
      { factKey: fact.key, patch: { superseded_by: supersedeTarget } },
      { onSuccess: () => setSupersedeOpen(false) },
    );
  };
  const clearSupersede = () => clearOverride.mutate({ factKey: fact.key, field: "superseded_by" });

  return (
    <Card data-testid={`memory-fact-${fact.slug}`}>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{fact.title}</span>
              <Badge variant="secondary">{t(`memory.factType.${fact.type}`)}</Badge>
              {fact.status === "superseded" ? (
                <Badge variant="outline">
                  {fact.proposed
                    ? t("memory.status.proposedSupersede")
                    : t("memory.status.settledSupersede")}
                </Badge>
              ) : null}
              {fact.conflicts_with.length > 0 ? (
                <Badge
                  variant="outline"
                  className="border-status-warn/40 bg-status-warn/10 text-status-warn"
                >
                  {t("memory.status.conflicting")}
                </Badge>
              ) : null}
              {fact.hidden ? (
                <Badge variant="outline">{t("memory.status.hiddenBadge")}</Badge>
              ) : null}
              {fact.pinned ? (
                <Badge variant="outline">{t("memory.status.pinnedBadge")}</Badge>
              ) : null}
            </div>
            <p className="text-sm text-muted-foreground">{fact.description}</p>
          </div>

          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={busy}
              aria-label={fact.hidden ? t("memory.unhide") : t("memory.hide")}
              title={fact.hidden ? t("memory.unhide") : t("memory.hide")}
              onClick={toggleHidden}
            >
              {fact.hidden ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={busy}
              aria-label={fact.pinned ? t("memory.unpin") : t("memory.pin")}
              title={fact.pinned ? t("memory.unpin") : t("memory.pin")}
              onClick={togglePinned}
            >
              {fact.pinned ? (
                <Pin className="size-4 fill-current" />
              ) : (
                <PinOff className="size-4" />
              )}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={() => setShowOrigins((v) => !v)}>
            {showOrigins ? (
              <ChevronDown className="mr-1 size-3.5" />
            ) : (
              <ChevronRight className="mr-1 size-3.5" />
            )}
            {showOrigins ? t("memory.origins.hide") : t("memory.origins.show")}
          </Button>

          {settledSupersede ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={clearSupersede}
              disabled={busy}
            >
              {t("memory.supersede.clear", { target: override?.superseded_by })}
            </Button>
          ) : candidates.length > 0 ? (
            <Popover open={supersedeOpen} onOpenChange={setSupersedeOpen}>
              <PopoverTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  {t("memory.supersede.action")}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-72 space-y-2">
                <Select value={supersedeTarget} onValueChange={setSupersedeTarget}>
                  <SelectTrigger>
                    <SelectValue placeholder={t("memory.supersede.pickPlaceholder")} />
                  </SelectTrigger>
                  <SelectContent>
                    {candidates.map((c) => (
                      <SelectItem key={c.key} value={c.key}>
                        {c.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  size="sm"
                  className="w-full"
                  disabled={!supersedeTarget || busy}
                  onClick={applySupersede}
                >
                  {t("memory.supersede.apply")}
                </Button>
              </PopoverContent>
            </Popover>
          ) : null}
        </div>

        {showOrigins ? (
          <div
            className="space-y-2 rounded-md border border-border/60 bg-muted/30 p-3"
            data-testid={`memory-fact-origins-${fact.slug}`}
          >
            {detail.isPending ? (
              <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
            ) : detail.error ? (
              <p className="text-sm text-destructive">{t("memory.origins.loadFailed")}</p>
            ) : (
              <>
                <p className="whitespace-pre-wrap text-sm">{detail.data?.body}</p>
                <ul className="space-y-1">
                  {detail.data?.origins.map((o, i) => (
                    <li
                      key={`${o.agent}-${o.anchor}-${i}`}
                      className="text-xs text-muted-foreground"
                    >
                      <Badge variant="outline" className="mr-1.5">
                        {o.agent}
                      </Badge>
                      <span className="font-mono">{o.native_path}</span>
                      {" · "}
                      {new Date(o.captured_at).toLocaleString()}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
