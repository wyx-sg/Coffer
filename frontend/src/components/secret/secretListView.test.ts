// src/components/secret/secretListView.test.ts — the Secrets list's short names, filters, default order and URL state.
import { describe, expect, test } from "vitest";

import type { SecretRef } from "@/lib/api/secret";
import { parseListState, withListState, type SecretListState } from "@/lib/secrets/listState";
import { shortName } from "./secretRows";
import { decorate, defaultOrder, filterItems, isDeletable } from "./secretListView";

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
  ...over,
});

const JIRA = ref({
  ref: "mcp_server/26dddfa9ff00/JIRA_PERSONAL_TOKEN",
  cited_by: [{ kind: "mcp_server", name: "jira", uid: "26dd" }],
});
const SEATALK = ref({
  ref: "channel/4c838e8fa72e/app-secret",
  cited_by: [{ kind: "channel", name: "seatalk", uid: "4c83" }],
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

describe("secret names", () => {
  test("a ref shows its last segment, and a dotted name drops its owner's prefix", () => {
    expect(shortName(JIRA)).toBe("JIRA_PERSONAL_TOKEN");
    expect(shortName(SEATALK)).toBe("app-secret");
    expect(shortName(GROQ)).toBe("key");
    expect(shortName(POSTMAN)).toBe("AUTHORIZATION");
    expect(shortName(ref({ ref: "aws.access_key" }))).toBe("aws.access_key");
  });
});

describe("secret list view", () => {
  const items = decorate(ALL, new Set([GROQ.ref]));

  test("status keeps in use or not used", () => {
    const only = (status: SecretListState["status"]) =>
      filterItems(items, state({ status })).map((i) => i.short);
    expect(only("unused")).toEqual(["old-key"]);
    expect(only("inUse")).toHaveLength(4);
    expect(only("all")).toHaveLength(5);
  });

  test("search matches the ref, the short name and the names of what uses it", () => {
    const names = (s: SecretListState) => filterItems(items, s).map((i) => i.short);
    expect(names(state({ q: "jira" }))).toEqual(["JIRA_PERSONAL_TOKEN"]);
    expect(names(state({ q: "APP-SEC" }))).toEqual(["app-secret"]);
    expect(names(state({ q: "groq" }))).toEqual(["key"]);
  });

  test("the default order puts no-value and waiting rows first, then names", () => {
    const withMissing = decorate(
      [...ALL, ref({ ref: "secret/zeta", uri: "coffer://secret/zeta", present: false })],
      new Set([GROQ.ref]),
    );
    expect(defaultOrder(withMissing).map((i) => i.short)).toEqual([
      "key",
      "zeta",
      "app-secret",
      "AUTHORIZATION",
      "JIRA_PERSONAL_TOKEN",
      "old-key",
    ]);
  });

  test("only a stored secret nothing uses and nothing waits on can be deleted", () => {
    expect(items.filter(isDeletable).map((i) => i.short)).toEqual(["old-key"]);
    const waiting = decorate([OLD], new Set([OLD.ref]));
    expect(isDeletable(waiting[0])).toBe(false);
  });
});

describe("secret list state in the URL", () => {
  test("defaults are not spelled out, the sort is left alone, and the state round-trips", () => {
    expect(withListState(new URLSearchParams(), state()).toString()).toBe("");
    const s = state({ q: "jira", status: "unused" });
    const params = withListState(new URLSearchParams("sort=created"), s);
    expect(params.get("sort")).toBe("created");
    expect(parseListState(params)).toEqual(s);
    expect(withListState(params, state()).toString()).toBe("sort=created");
  });

  test("an unknown status falls back to all", () => {
    expect(parseListState(new URLSearchParams("status=pending&kind=x"))).toEqual(state());
  });
});
