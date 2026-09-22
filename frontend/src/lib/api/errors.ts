// frontend/src/lib/api/errors.ts
//
// Typed error wrapper so hooks can preserve the API error code and
// components / translators can map `errors.<CODE>` keys in i18n.

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly envelopeMessage: string,
    public readonly details?: unknown,
  ) {
    super(envelopeMessage);
    this.name = "ApiError";
  }
}

/**
 * The envelope code the daemon answers a request it is not ready for with
 * (backend `surfaces/http/errors.py`), reused here for the request that never
 * left: a page whose supplier has not named a base URL yet is in exactly that
 * state, and saying so in the daemon's own vocabulary means the offline banner
 * and the `errors.DAEMON_NOT_READY` translation already know what to do with
 * it. See `getCofferBaseUrl`.
 */
const DAEMON_NOT_READY = "DAEMON_NOT_READY";

/** The error a caller raises when no base URL has been supplied yet. */
export function daemonNotReadyError(): ApiError {
  return new ApiError(DAEMON_NOT_READY, "the daemon connection has not been supplied yet");
}

/**
 * The same thing as a response, for the one caller that short-circuits inside
 * `fetch` rather than before it — the generated client's middleware, which can
 * return a `Response` but cannot throw one.
 */
export function daemonNotReadyResponse(): Response {
  return new Response(
    JSON.stringify({
      error: {
        code: DAEMON_NOT_READY,
        message: "the daemon connection has not been supplied yet",
        details: {},
      },
    }),
    { status: 503, headers: { "Content-Type": "application/json" } },
  );
}

/** The error envelope shape openapi-fetch returns on a non-2xx response. */
type ErrorEnvelope =
  | { error?: { code?: string; message?: string; details?: unknown } }
  | undefined;

/**
 * Throw a typed {@link ApiError} from an openapi-fetch error envelope,
 * falling back to `code`/`message` when the envelope is absent. Centralises
 * the `error.error?.code ?? …` unwrap that every query/mutation hook repeats.
 * Plumbs the envelope's `details` (e.g. an `IngestRejected` `reason`) onto the
 * thrown error so {@link translateApiError} can pick a reason-specific message.
 */
export function throwApiError(envelope: ErrorEnvelope, code: string, message: string): never {
  throw new ApiError(
    envelope?.error?.code ?? code,
    envelope?.error?.message ?? message,
    envelope?.error?.details,
  );
}

/**
 * Map an API error to a translated string.
 *
 * 1. If the error is an ApiError with a string `details.reason`, first try the
 *    reason-qualified key `errors.<code>_<reason>` (a flat key — `errors.<code>`
 *    is itself a string, so a nested object key is impossible). Use it when it
 *    resolves; otherwise fall through to the code-level lookup.
 * 2. Try `errors.<code>` in the translation namespace.  Fall back to the raw
 *    envelope message when the key is not found (i.e. it resolves to itself).
 * 3. For plain Error instances, return `error.message`.
 * 4. For unknown values, coerce to string.
 */
export function translateApiError(t: (key: string) => string, error: unknown): string {
  if (error instanceof ApiError) {
    const { details } = error;
    const reason =
      details && typeof details === "object" && "reason" in details
        ? (details as { reason?: unknown }).reason
        : undefined;
    if (typeof reason === "string") {
      const reasonKey = `errors.${error.code}_${reason}`;
      const reasonTranslated = t(reasonKey);
      // i18next returns the key itself when a translation is missing
      if (reasonTranslated !== reasonKey) return reasonTranslated;
    }
    const key = `errors.${error.code}`;
    const translated = t(key);
    return translated === key ? error.envelopeMessage : translated;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}
