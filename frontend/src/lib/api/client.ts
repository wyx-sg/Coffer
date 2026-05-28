import createClient from "openapi-fetch";
import type { paths } from "./types";
import { getCofferToken, getCofferBaseUrl } from "../auth";

let _client: ReturnType<typeof createClient<paths>> | null = null;

export function getApiClient(): ReturnType<typeof createClient<paths>> {
  if (_client !== null) return _client;
  _client = createClient<paths>({
    baseUrl: getCofferBaseUrl(),
    headers: {
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
  });
  return _client;
}

/** Call when the auth token changes so the next request re-reads it. */
export function resetApiClient(): void {
  _client = null;
}
