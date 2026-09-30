// src/components/custom-tools/ToolTestResult.test.tsx — each way a test run can end reads as the canvas
// boards do: an answer, the API's error, a rejected secret, a timeout, no connection, a response cut short.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import type { CustomToolTestOut } from "@/lib/api/customTools";
import { ToolTestResult } from "./ToolTestResult";

const URL = "https://deploy.internal.example/v1/services/web/health?env=staging";

function result(patch: Partial<CustomToolTestOut>): CustomToolTestOut {
  return {
    ok: true,
    duration_ms: 180,
    url: URL,
    status: 200,
    status_line: "HTTP 200 OK",
    body: '{"healthy":true}',
    truncated: false,
    content_type: "application/json",
    error: null,
    failure: null,
    ...patch,
  };
}

const show = (r: CustomToolTestOut) =>
  render(
    <ToolTestResult
      result={r}
      method="GET"
      group="deploy-api"
      secret="deploy-token"
      timeoutSeconds={30}
    />,
  );

describe("ToolTestResult", () => {
  test("an answer shows its status, time, size and kind, the URL and the body", () => {
    show(result({}));
    expect(screen.getByText("200 OK in 180 ms · 16 B JSON")).toBeInTheDocument();
    expect(screen.getByText(URL)).toBeInTheDocument();
    expect(screen.getByText('{"healthy":true}')).toBeInTheDocument();
  });

  test("an error answer keeps the body and says nothing was saved", () => {
    show(
      result({
        ok: false,
        status: 404,
        status_line: "HTTP 404 Not Found",
        body: '{"error":"unknown_service"}',
      }),
    );
    expect(screen.getByText(/404 Not Found in 180 ms/)).toBeInTheDocument();
    expect(screen.getByText('{"error":"unknown_service"}')).toBeInTheDocument();
    expect(screen.getByText(/The API answered with an error/)).toBeInTheDocument();
  });

  test("a rejected secret names the secret and the group that shares it", () => {
    show(result({ ok: false, status: 401, status_line: "HTTP 401 Unauthorized", body: "" }));
    expect(screen.getByText(/The API rejected deploy-token/)).toBeInTheDocument();
    expect(screen.getByText(/every tool in deploy-api uses the same secret/)).toBeInTheDocument();
  });

  test("a timeout names the group's timeout", () => {
    show(result({ ok: false, status: null, status_line: null, body: "", failure: "timeout" }));
    expect(screen.getByText("No response — timed out after 30 s")).toBeInTheDocument();
    expect(screen.getByText(/raise the timeout in Edit group/)).toBeInTheDocument();
  });

  test("no connection names the host", () => {
    show(result({ ok: false, status: null, status_line: null, body: "", failure: "connect" }));
    expect(screen.getByText("Couldn't connect to deploy.internal.example")).toBeInTheDocument();
    expect(screen.getByText(/check it reaches deploy.internal.example/)).toBeInTheDocument();
  });

  test("a response cut short says agents get the same first megabyte", () => {
    show(result({ truncated: true }));
    expect(screen.getByText("Response cut short at 1 MB")).toBeInTheDocument();
    expect(screen.getByText(/Agents get the same first 1 MB/)).toBeInTheDocument();
  });
});
