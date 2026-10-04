// frontend/src/components/channel/ChannelPeopleList.tsx
// The people a channel answers, one row each: who they are on the platform, when
// they were paired, and Remove. Past a few owners a search box filters them by
// name, and the list scrolls inside a fixed-height window. Add owner opens the
// pairing dialog (the caller's); the list prints nothing of the flow itself. Every person is an owner with the
// same rights — the daemon treats them identically — so no row carries a
// different role.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import type { ChannelPerson } from "@/lib/api/channels";

/** More owners than this and the list gets a search box. */
const SEARCH_FROM = 5;

/** "Sep 12" — the short US date (the Chinese UI gets its own short form). */
function pairedOn(iso: string, language: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(language.startsWith("zh") ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
  }).format(d);
}

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : name.slice(0, 2);
  return letters.toUpperCase();
}

interface Props {
  people: readonly ChannelPerson[];
  /** Whether Add owner is on offer (not while the channel cannot pair yet). */
  canAdd: boolean;
  onAdd: () => void;
  onRemove: (person: ChannelPerson) => void;
}

export function ChannelPeopleList({ people, canAdd, onAdd, onRemove }: Props) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState("");
  // With only a few owners the list is its own answer; a search box earns its
  // place once it is long.
  const searchable = people.length > SEARCH_FROM;
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? people.filter((p) => p.display_name.toLowerCase().includes(q)) : people;
  }, [people, query]);
  return (
    <>
      {searchable ? (
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t("channels.overview.who.search")}
          ariaLabel={t("channels.overview.who.search")}
        />
      ) : null}
      {people.length > 0 && shown.length === 0 ? (
        <p className="text-sm text-text-muted">{t("channels.overview.who.noMatch")}</p>
      ) : null}
      {shown.length > 0 ? (
        // A fixed-height window: a long list scrolls inside it instead of
        // pushing the rest of the page down.
        <ul
          className="flex max-h-[19rem] flex-col overflow-y-auto overscroll-contain rounded-lg border border-border-subtle"
          aria-label={t("channels.overview.who.title")}
          data-testid="channel-owners-scroll"
        >
          {shown.map((person) => (
            <li
              key={person.sender_id}
              className="flex min-h-[46px] items-center gap-2.5 border-t border-border-subtle px-3 first:border-t-0"
              data-testid="channel-owner"
            >
              <span
                aria-hidden
                className="inline-flex size-[26px] shrink-0 items-center justify-center rounded-md bg-chip text-2xs font-semibold text-text-muted"
              >
                {initials(person.display_name)}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-label">{person.display_name}</span>
                <span className="text-xs text-text-muted">
                  {t("channels.overview.who.ownerLine", {
                    date: pairedOn(person.paired_at, i18n.language),
                  })}
                </span>
              </span>
              <span className="ml-auto flex shrink-0 gap-1">
                <Button size="sm" variant="ghost" onClick={() => onRemove(person)}>
                  {t("channels.overview.who.remove")}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      ) : people.length === 0 ? (
        <p className="rounded-lg border border-border-subtle px-3 py-3 text-sm text-text-muted">
          {t("channels.overview.who.nobody")}
        </p>
      ) : null}
      {canAdd ? (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button size="sm" variant="secondary" onClick={onAdd}>
            <Plus aria-hidden />
            {t("channels.overview.who.addOwner")}
          </Button>
        </div>
      ) : null}
    </>
  );
}
