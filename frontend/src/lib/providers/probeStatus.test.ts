// src/lib/providers/probeStatus.test.ts — health read from the endpoint-models probe.
import { describe, expect, test } from "vitest";

import { authStatusOf, probeFailed, probeStatus } from "./probeStatus";

const answer = (models: unknown[], message: string, reachable: boolean) => ({
  models,
  message,
  reachable,
});

describe("probeStatus", () => {
  test("a reachable endpoint is reachable, with models or with none", () => {
    expect(probeStatus({ data: answer([1], "", true), error: null, pending: false })).toBe(
      "reachable",
    );
    expect(
      probeStatus({
        data: answer([], "the endpoint listed no models", true),
        error: null,
        pending: false,
      }),
    ).toBe("reachable");
  });

  test("an unreachable answer naming 401 or 403 is a rejected key", () => {
    const message = "Client error '401 Unauthorized' for url 'https://gw/v1/models'";
    expect(probeStatus({ data: answer([], message, false), error: null, pending: false })).toBe(
      "keyRejected",
    );
    expect(authStatusOf(message)).toBe("401");
  });

  test("any other failure, or a failed request, is unreachable", () => {
    expect(
      probeStatus({
        data: answer([], "All connection attempts failed", false),
        error: null,
        pending: false,
      }),
    ).toBe("unreachable");
    expect(probeStatus({ data: undefined, error: new Error("x"), pending: false })).toBe(
      "unreachable",
    );
    expect(probeStatus({ data: undefined, error: null, pending: true })).toBe("checking");
  });

  test("a failed listing is an error or an unreachable answer, never an empty catalogue", () => {
    expect(probeFailed(answer([], "the endpoint listed no models", true), null)).toBe(false);
    expect(probeFailed(answer([], "boom", false), null)).toBe(true);
    expect(probeFailed(undefined, new Error("x"))).toBe(true);
  });
});
