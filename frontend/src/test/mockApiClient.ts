// frontend/src/test/mockApiClient.ts
//
// Shared helper to mock @/lib/api/client.getApiClient() across vitest
// suites. Replaces the 25+ ad-hoc `vi.mock("@/lib/api/client", …)` blocks
// scattered through *.test.tsx files with a single typed entry point.
//
// Why a separate helper:
//   * Cuts boilerplate — every consumer used the same 3-line stanza
//     (vi.mock → vi.mocked → assemble verbs).
//   * Forces a single contract for the four verbs (GET/POST/PATCH/DELETE),
//     so a future schema change shows up in one place, not 25.
//   * Lets each test override only the verb it cares about while still
//     stubbing the others as safe no-op resolvers.
//
// Usage:
//
//   import { vi } from "vitest";
//   import { mockApiClient } from "@/test/mockApiClient";
//
//   const api = mockApiClient({
//     GET: vi.fn().mockResolvedValue({ data: …, error: undefined }),
//   });
//
//   // assert later: expect(api.POST).toHaveBeenCalled();
//
// Tests must still call vi.mock("@/lib/api/client", () => ({ … })) at
// module scope because vitest hoists vi.mock; that part is unavoidable.
// This helper just builds the verb-bag.

import type { Mock } from "vitest";
import { vi } from "vitest";

type VerbResult = { data?: unknown; error?: unknown };
type VerbMock = Mock<(path: string, init?: unknown) => Promise<VerbResult>>;

export interface ApiClientMock {
  GET: VerbMock;
  POST: VerbMock;
  PATCH: VerbMock;
  DELETE: VerbMock;
}

export interface VerbOverrides {
  GET?: VerbMock;
  POST?: VerbMock;
  PATCH?: VerbMock;
  DELETE?: VerbMock;
}

/** Default verb mock that resolves to `{ data: undefined, error: undefined }`. */
function defaultVerb(): VerbMock {
  return vi.fn().mockResolvedValue({ data: undefined, error: undefined }) as VerbMock;
}

/**
 * Build a typed mock for `getApiClient()`'s return value. Each verb falls
 * back to a safe no-op resolver when not overridden.
 */
export function mockApiClient(overrides: VerbOverrides = {}): ApiClientMock {
  return {
    GET: overrides.GET ?? defaultVerb(),
    POST: overrides.POST ?? defaultVerb(),
    PATCH: overrides.PATCH ?? defaultVerb(),
    DELETE: overrides.DELETE ?? defaultVerb(),
  };
}
