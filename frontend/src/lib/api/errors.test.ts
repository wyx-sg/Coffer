// frontend/src/lib/api/errors.test.ts
//
// translateApiError lets a machine `reason` (carried in the envelope's
// `details`) drive a specific user message via a flat reason-qualified i18n
// key `errors.<code>_<reason>`, falling back to the code-level message when no
// such key exists — backward-compatible with errors that carry no reason.

import { describe, expect, test } from "vitest";
import { ApiError, throwApiError, translateApiError } from "./errors";

// A stub `t` that mirrors i18next's contract: return the translation for a
// known key, otherwise echo the key back (signalling "missing").
function makeT(table: Record<string, string>): (key: string) => string {
  return (key: string) => table[key] ?? key;
}

const TABLE = {
  "errors.INGEST_REJECTED": "The document was rejected during ingestion",
  "errors.INGEST_REJECTED_scanned_pdf": "This PDF appears to be scanned or image-only — run OCR.",
};

describe("throwApiError", () => {
  test("throws an ApiError carrying the envelope details (reason)", () => {
    try {
      throwApiError(
        {
          error: {
            code: "INGEST_REJECTED",
            message: "rejected",
            details: { reason: "scanned_pdf" },
          },
        },
        "FALLBACK",
        "fallback message",
      );
      throw new Error("expected throwApiError to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe("INGEST_REJECTED");
      expect(apiErr.envelopeMessage).toBe("rejected");
      expect(apiErr.details).toEqual({ reason: "scanned_pdf" });
    }
  });

  test("falls back to code/message and undefined details when envelope is absent", () => {
    try {
      throwApiError(undefined, "FALLBACK", "fallback message");
      throw new Error("expected throwApiError to throw");
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe("FALLBACK");
      expect(apiErr.envelopeMessage).toBe("fallback message");
      expect(apiErr.details).toBeUndefined();
    }
  });
});

describe("translateApiError", () => {
  test("(a) uses the reason-qualified key when it resolves", () => {
    const t = makeT(TABLE);
    const err = new ApiError("INGEST_REJECTED", "generic envelope", { reason: "scanned_pdf" });
    expect(translateApiError(t, err)).toBe(
      "This PDF appears to be scanned or image-only — run OCR.",
    );
  });

  test("(b) falls back to errors.<code> when no reason-qualified key exists", () => {
    const t = makeT(TABLE);
    const err = new ApiError("INGEST_REJECTED", "generic envelope", { reason: "too_large" });
    expect(translateApiError(t, err)).toBe("The document was rejected during ingestion");
  });

  test("(b') falls back to the envelope message when neither key exists", () => {
    const t = makeT(TABLE);
    const err = new ApiError("UNKNOWN_CODE", "raw envelope message", { reason: "whatever" });
    expect(translateApiError(t, err)).toBe("raw envelope message");
  });

  test("(c) behaves exactly as before when there are no details/reason", () => {
    const t = makeT(TABLE);
    const withCodeKey = new ApiError("INGEST_REJECTED", "generic envelope");
    expect(translateApiError(t, withCodeKey)).toBe("The document was rejected during ingestion");

    const withoutCodeKey = new ApiError("UNKNOWN_CODE", "raw envelope message");
    expect(translateApiError(t, withoutCodeKey)).toBe("raw envelope message");
  });

  test("ignores a non-string reason and falls through to the code lookup", () => {
    const t = makeT(TABLE);
    const err = new ApiError("INGEST_REJECTED", "generic envelope", { reason: 42 });
    expect(translateApiError(t, err)).toBe("The document was rejected during ingestion");
  });

  test("plain Error returns its message; unknown values coerce to string", () => {
    const t = makeT(TABLE);
    expect(translateApiError(t, new Error("boom"))).toBe("boom");
    expect(translateApiError(t, 123)).toBe("123");
  });
});
