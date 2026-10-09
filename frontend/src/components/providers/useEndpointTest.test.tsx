// src/components/providers/useEndpointTest.test.tsx — a dialog's Test: a stored key refused for a new endpoint is a refusal, not a failed probe.
//
// Real QueryClientProvider and translations; only the api module is mocked.
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, render, renderHook, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api/errors";
import { ProbeResult } from "./ProbeResult";
import { useEndpointTest, type EndpointTestResult } from "./useEndpointTest";

vi.mock("@/lib/api/providers", () => ({ modelProbeApi: { list: vi.fn() } }));
const { modelProbeApi } = await import("@/lib/api/providers");
const list = vi.mocked(modelProbeApi.list);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

async function runProbe(): Promise<EndpointTestResult> {
  const { result } = renderHook(
    () => {
      const { t } = useTranslation();
      return useEndpointTest(t);
    },
    { wrapper },
  );
  let out: EndpointTestResult | undefined;
  await act(async () => {
    out = await result.current.run({
      provider: "openai",
      base_url: "http://new.test/v1",
      secret_ref: "secret/a",
    });
  });
  return out!;
}

const FAIL_NOTE = "Check the key is for this endpoint and hasn't been revoked. Nothing was saved.";

afterEach(() => vi.clearAllMocks());

describe("useEndpointTest", () => {
  test("a stored key refused for this endpoint reads as a refusal, with its remedy", async () => {
    list.mockRejectedValue(
      new ApiError("CONFIG_INVALID", "a stored key can be tried only ...", {
        reason: "stored_key_destination",
      }),
    );
    const result = await runProbe();
    expect(result.kind).toBe("refused");
    render(
      <ProbeResult result={result} pending={false} okNote={() => null} failNote={FAIL_NOTE} />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Not tested: this stored key can't go to this endpoint yet");
    expect(alert).toHaveTextContent("so nothing was sent");
    expect(alert).toHaveTextContent("paste the key");
    // Nothing points at an unreachable endpoint or a revoked key.
    expect(alert).not.toHaveTextContent("Couldn't reach the endpoint");
    expect(alert).not.toHaveTextContent("revoked");
  });

  test("any other error is still a failed test with the dialog's note", async () => {
    list.mockRejectedValue(new ApiError("CONFIG_INVALID", "bad url"));
    const result = await runProbe();
    expect(result.kind).toBe("failed");
    render(
      <ProbeResult result={result} pending={false} okNote={() => null} failNote={FAIL_NOTE} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't reach the endpoint");
    expect(screen.getByRole("alert")).toHaveTextContent("revoked");
  });
});
