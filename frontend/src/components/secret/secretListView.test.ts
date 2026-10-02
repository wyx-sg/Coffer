// src/components/secret/secretListView.test.ts — the Secrets list's owners, short names, filters, sort, counts and groups.
import { describe, expect, test } from "vitest";

import type { SecretRef } from "@/lib/api/secret";
import { listStateParams, parseListState, type SecretListState } from "@/lib/secrets/listState";
import { ownerOf, shortName } from "./secretOwners";
import {
  decorate,
  groupByOwner,
  isDeletable,
  matchesStatus,
  searchAndKind,
  sortItems,
  statusCounts,
} from "./secretListView";

function ref(over: Partial<SecretRef> & { ref: string }): SecretRef {
  return {
    bindings: [],
    cited_by: [],
    mentioned_by_skills: [],
    present: true,
    locked: false,
    created_at: null,
    last_used_at: null,
    readable_by_local_processes: false,
    unreferenced: false,
    uri: null,
    ...over,
  };
}

const state = (over: Partial<SecretListState> = {}): SecretListState => ({
  q: "",
  status: "all",
  kind: "all",
  sort: null,
  dir: "asc",
  view: "list",
  ...over,
});

const JIRA = ref({
  ref: "mcp_server/26dddfa9ff00/JIRA_PERSONAL_TOKEN",
  cited_by: [{ kind: "mcp_server", name: "jira", uid: "26dd" }],
  last_used_at: "2026-09-30T10:00:00Z",
  created_at: "2026-08-01T10:00:00Z",
});
const SEATALK = ref({
  ref: "channel/4c838e8fa72e/app-secret",
  cited_by: [{ kind: "channel", name: "seatalk", uid: "4c83" }],
  created_at: "2026-09-01T10:00:00Z",
});
const GROQ = ref({
  ref: "provider/b7b7526c/key",
  cited_by: [{ kind: "provider", name: "groq", uid: "b7b7" }],
});
const POSTMAN = ref({
  ref: "postman.AUTHORIZATION",
  cited_by: [{ kind: "custom_tool", name: "postman", uid: "p1" }],
});
const OLD = ref({ ref: "secret/old-key", uri: "coffer://secret/old-key", unreferenced: true });
const ALL = [JIRA, SEATALK, GROQ, POSTMAN, OLD];

describe("secret owners", () => {
  test("a ref shows its last segment, and a dotted name drops its owner's prefix", () => {
    expect(shortName(JIRA)).toBe("JIRA_PERSONAL_TOKEN");
    expect(shortName(SEATALK)).toBe("app-secret");
    expect(shortName(GROQ)).toBe("key");
    expect(shortName(POSTMAN)).toBe("AUTHORIZATION");
    expect(shortName(ref({ ref: "aws.access_key" }))).toBe("aws.access_key");
  });

  test("the owner is the first citer; a sync remote counts as sync; nothing citing it is none", () => {
    expect(ownerOf(JIRA)).toMatchObject({ kind: "mcp_server", name: "jira", more: 0 });
    expect(
      ownerOf(ref({ ref: "x", cited_by: [{ kind: "sync_remote", name: "git", uid: "r" }] })).kind,
    ).toBe("sync");
    expect(
      ownerOf(ref({ ref: "x", cited_by: [{ kind: "agent", name: "a", uid: "u" }] })).kind,
    ).toBe("other");
    expect(ownerOf(OLD)).toMatchObject({ key: "none", name: null });
    expect(ownerOf(ref({ ref: "channel/u/app-secret", unreferenced: true })).kind).toBe("channel");
  });
});

describe("secret list view", () => {
  const items = decorate(ALL, new Set([GROQ.ref]), new Set([SEATALK.ref]));

  test("status filters and their counts", () => {
    expect(statusCounts(items)).toEqual({ all: 5, inUse: 4, unused: 1, pending: 1, refused: 1 });
    const only = (status: SecretListState["status"]) =>
      items.filter((i) => matchesStatus(i, status)).map((i) => i.short);
    expect(only("unused")).toEqual(["old-key"]);
    expect(only("pending")).toEqual(["key"]);
    expect(only("refused")).toEqual(["app-secret"]);
  });

  test("search matches the ref, the short name and the owner's name; the kind narrows by owner", () => {
    const names = (s: SecretListState) => searchAndKind(items, s).map((i) => i.short);
    expect(names(state({ q: "jira" }))).toEqual(["JIRA_PERSONAL_TOKEN"]);
    expect(names(state({ q: "APP-SEC" }))).toEqual(["app-secret"]);
    expect(names(state({ kind: "provider" }))).toEqual(["key"]);
    expect(names(state({ kind: "other" }))).toEqual(["old-key"]);
  });

  test("the default order puts what waits for approval first, then names; a column sorts both ways", () => {
    expect(sortItems(items, state()).map((i) => i.short)).toEqual([
      "key",
      "app-secret",
      "AUTHORIZATION",
      "JIRA_PERSONAL_TOKEN",
      "old-key",
    ]);
    expect(sortItems(items, state({ sort: "name" })).map((i) => i.short)[0]).toBe("app-secret");
    expect(sortItems(items, state({ sort: "name", dir: "desc" })).map((i) => i.short)[0]).toBe(
      "old-key",
    );
    expect(sortItems(items, state({ sort: "created", dir: "desc" })).map((i) => i.short)[0]).toBe(
      "app-secret",
    );
    expect(sortItems(items, state({ sort: "lastUsed", dir: "desc" })).map((i) => i.short)[0]).toBe(
      "JIRA_PERSONAL_TOKEN",
    );
  });

  test("only a stored secret nothing uses and nothing waits on can be deleted", () => {
    expect(items.filter(isDeletable).map((i) => i.short)).toEqual(["old-key"]);
    const waiting = decorate([OLD], new Set([OLD.ref]), new Set());
    expect(isDeletable(waiting[0])).toBe(false);
  });

  test("groups by owner, with what nothing uses last", () => {
    const groups = groupByOwner(items);
    expect(groups.map((g) => g.key)).toEqual([
      "mcp_server:26dd",
      "channel:4c83",
      "provider:b7b7",
      "custom_tool:p1",
      "none",
    ]);
    expect(groups.at(-1)!.items.map((i) => i.short)).toEqual(["old-key"]);
  });
});

describe("secret list state in the URL", () => {
  test("defaults are not spelled out and the state round-trips", () => {
    expect(listStateParams(state(), "list").toString()).toBe("");
    const s = state({ q: "jira", status: "unused", kind: "mcp_server", sort: "name", dir: "desc" });
    const params = listStateParams(s, "list");
    expect(parseListState(params, "list")).toEqual(s);
  });

  test("the view is written unless it is the list the browser also opens", () => {
    expect(listStateParams(state({ view: "owner" }), "list").get("view")).toBe("owner");
    expect(listStateParams(state({ view: "owner" }), "owner").get("view")).toBe("owner");
    expect(listStateParams(state({ view: "list" }), "list").has("view")).toBe(false);
    expect(listStateParams(state({ view: "list" }), "owner").get("view")).toBe("list");
    expect(parseListState(new URLSearchParams(), "owner").view).toBe("owner");
    expect(parseListState(new URLSearchParams("status=bogus&kind=x&sort=y"), "list")).toEqual(
      state(),
    );
  });
});
