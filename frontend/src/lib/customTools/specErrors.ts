// src/lib/customTools/specErrors.ts — reading the error a spec read answers with.
import { ApiError } from "@/lib/api/errors";

/** Whether the error is a spec URL that did not answer. */
export function isUnreachable(error: unknown): boolean {
  return error instanceof ApiError && error.code === "OPENAPI_UNREACHABLE";
}
