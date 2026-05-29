// frontend/src/lib/api/errors.ts
//
// Typed error wrapper so hooks can preserve the API error code and
// components / translators can map `errors.<CODE>` keys in i18n.

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly envelopeMessage: string,
  ) {
    super(envelopeMessage);
    this.name = "ApiError";
  }
}

/** The error envelope shape openapi-fetch returns on a non-2xx response. */
type ErrorEnvelope = { error?: { code?: string; message?: string } } | undefined;

/**
 * Throw a typed {@link ApiError} from an openapi-fetch error envelope,
 * falling back to `code`/`message` when the envelope is absent. Centralises
 * the `error.error?.code ?? …` unwrap that every query/mutation hook repeats.
 */
export function throwApiError(envelope: ErrorEnvelope, code: string, message: string): never {
  throw new ApiError(envelope?.error?.code ?? code, envelope?.error?.message ?? message);
}

/**
 * Map an API error to a translated string.
 *
 * 1. If the error is an ApiError, try `errors.<code>` in the translation
 *    namespace.  Fall back to the raw envelope message when the key is
 *    not found (i.e. the key resolves to itself).
 * 2. For plain Error instances, return `error.message`.
 * 3. For unknown values, coerce to string.
 */
export function translateApiError(t: (key: string) => string, error: unknown): string {
  if (error instanceof ApiError) {
    const key = `errors.${error.code}`;
    const translated = t(key);
    // i18next returns the key itself when a translation is missing
    return translated === key ? error.envelopeMessage : translated;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}
