// src/lib/activity/export.test.ts — the export writes every matching record through each log's own route.
import { beforeEach, expect, test, vi } from "vitest";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const { collectForExport, toCsv, toJson } = await import("./export");
const { fromCall } = await import("./records");

const call = (id: number, status: "ok" | "error") => ({
  id,
  timestamp: `2026-09-29T14:0${id}:00Z`,
  resource_uid: "u-gh",
  resource_name: "github",
  capability_type: "tool" as const,
  capability_key: "search_code",
  duration_ms: 10,
  status,
  error_message: status === "error" ? 'refused, "hard"' : null,
  session_id: null,
  agent_uid: null,
  trace_id: null,
});

beforeEach(() => vi.mocked(getApiClient).mockReset());

test("the export pages through the route and keeps only what the predicate accepts", async () => {
  const get = vi
    .fn()
    .mockResolvedValueOnce({
      data: { invocations: [call(3, "error"), call(2, "ok")], next_cursor: "c1", total: 3 },
    })
    .mockResolvedValueOnce({
      data: { invocations: [call(1, "error")], next_cursor: null, total: 3 },
    });
  vi.mocked(getApiClient).mockReturnValue({ GET: get } as never);

  const records = await collectForExport(
    [{ source: "call", params: { uid: "u-gh", status: "error" } }],
    (r) => r.source === "call" && r.call.status === "error",
  );
  expect(records.map((r) => r.key)).toEqual(["call:3", "call:1"]);
  expect(get).toHaveBeenCalledTimes(2);
  const firstQuery = get.mock.calls[0][1].params.query;
  expect(firstQuery).toMatchObject({ uid: "u-gh", status: "error" });
  expect(get.mock.calls[1][1].params.query.cursor).toBe("c1");
});

test("CSV has a header, one row per record and quotes what needs quoting", () => {
  const csv = toCsv([fromCall(call(1, "error"))]);
  const lines = csv.trim().split("\r\n");
  expect(lines).toHaveLength(2);
  expect(lines[0].startsWith("time,source,event")).toBe(true);
  expect(lines[1]).toContain('"refused, ""hard"""');
});

test("JSON is the records as the daemon sent them, tagged with their log", () => {
  const parsed = JSON.parse(toJson([fromCall(call(1, "ok"))]));
  expect(parsed).toEqual([{ source: "mcp_call", ...call(1, "ok") }]);
});
