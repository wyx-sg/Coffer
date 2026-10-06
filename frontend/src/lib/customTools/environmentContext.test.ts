// src/lib/customTools/environmentContext.test.ts — the chosen environment and the request a form would send there,
// by the daemon's rules (domain/mcp/http_api_request.py).
import { describe, expect, test } from "vitest";

import type { CustomToolEnvironment } from "@/lib/api/customTools";
import {
  chooseEnvironment,
  effectiveTimeout,
  environmentSecret,
  firstEnabled,
  requestPreview,
} from "./environmentContext";

function env(overrides: Partial<CustomToolEnvironment>): CustomToolEnvironment {
  return {
    name: "test",
    description: "",
    enabled: true,
    base_url: "https://test.example/api/",
    headers: [],
    variables: {},
    timeout_seconds: null,
    secret_state: "none",
    pending_approvals: [],
    pending_secrets: [],
    rejected_approvals: [],
    rejected_secrets: [],
    ...overrides,
  };
}

const secretHeader = {
  name: "Authorization",
  value: null,
  scheme: "Bearer" as const,
  secret: "test-key",
  secret_state: "present" as const,
};

describe("chooseEnvironment", () => {
  const group = {
    environments: [env({ name: "off", enabled: false }), env({ name: "test" })],
  };
  test("starts at the first environment that is on", () => {
    expect(firstEnabled(group)).toBe("test");
    expect(firstEnabled({ environments: [env({ enabled: false })] })).toBe("");
  });
  test("reports an environment switched off or deleted instead of moving to another", () => {
    expect(chooseEnvironment(group, "test").state).toBe("ok");
    expect(chooseEnvironment(group, "off")).toMatchObject({ state: "disabled", name: "off" });
    expect(chooseEnvironment(group, "gone")).toEqual({ state: "deleted", name: "gone" });
    expect(chooseEnvironment(group, "")).toEqual({ state: "none" });
  });
});

test("the timeout is the environment's own, else the group's", () => {
  expect(effectiveTimeout({ timeout_seconds: 30 }, { timeout_seconds: 7 })).toEqual({
    seconds: 7,
    source: "environment",
  });
  expect(effectiveTimeout({ timeout_seconds: 30 }, { timeout_seconds: null })).toEqual({
    seconds: 30,
    source: "group",
  });
});

test("an environment's secret is its own; one with no secret header has none", () => {
  expect(environmentSecret(env({ headers: [secretHeader] }))).toBe("test-key");
  expect(environmentSecret(env({ headers: [] }))).toBeNull();
});

describe("requestPreview", () => {
  const e = env({
    headers: [
      { name: "X-Tenant", value: "tenant-test", scheme: null, secret: null, secret_state: "none" },
      secretHeader,
    ],
    variables: { region: "eu 1" },
  });

  test("fills {env:NAME} in the path and query and keeps {argument} holes", () => {
    const p = requestPreview(e, { path: "/v1/{env:region}/items/{id}?r={env:region}&q={q}" });
    expect(p.url).toBe("https://test.example/api/v1/eu%201/items/{id}?r=eu 1&q={q}");
    expect(p.missingVariables).toEqual([]);
  });

  test("a tool header replaces a plain one; the secret header comes last and wins over any spelling", () => {
    const p = requestPreview(e, {
      path: "/x",
      headers: { "X-Tenant": "mine-{env:region}", authorization: "Basic nope" },
    });
    expect(p.headers.map((h) => [h.name, h.value, h.from])).toEqual([
      ["X-Tenant", "mine-eu 1", "tool"],
      ["Authorization", null, "environment"],
    ]);
    expect(p.headers[1].secret?.secret).toBe("test-key");
  });

  test("names a variable the environment does not define", () => {
    expect(requestPreview(e, { path: "/{env:zone}" }).missingVariables).toEqual(["zone"]);
  });
});
