import { describe, expect, it } from "vitest";

import { argumentProblems, argumentUses, holesIn, joinPath, splitPath } from "./requestParts";

describe("requestParts", () => {
  it("reads argument holes but not environment variables", () => {
    expect(holesIn("/v1/{env:region}/items/{id}?q={id}")).toEqual(["id"]);
  });

  it("splits a path into its base and query pairs and joins it back", () => {
    const parts = splitPath("/customers/search?q={query}&limit={limit}&flag");
    expect(parts).toEqual({
      base: "/customers/search",
      query: [
        { key: "q", value: "{query}" },
        { key: "limit", value: "{limit}" },
        { key: "flag", value: "" },
      ],
    });
    expect(joinPath(parts.base, [...parts.query.slice(0, 2), { key: "", value: "" }])).toBe(
      "/customers/search?q={query}&limit={limit}",
    );
    expect(joinPath("/x", [])).toBe("/x");
  });

  it("says where each argument goes and which ones are unused or missing", () => {
    const uses = argumentUses({
      path: "/orgs/{org}/search?q={query}",
      headers: [{ key: "X-Trace", value: "{trace}" }],
      body: '{"note": "{note}"}',
      sendsBody: false,
    });
    expect(uses.get("org")).toEqual([{ where: "path", key: "" }]);
    expect(uses.get("query")).toEqual([{ where: "query", key: "q" }]);
    expect(uses.get("trace")).toEqual([{ where: "header", key: "X-Trace" }]);
    expect(uses.has("note")).toBe(false);
    expect(argumentProblems(["org", "query", "status", ""], uses)).toEqual({
      unused: ["status"],
      missing: ["trace"],
    });
  });
});
