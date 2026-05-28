import createClient from "openapi-fetch";
import type { paths } from "./types";
import { getCofferToken, getCofferBaseUrl } from "../auth";

let _client: ReturnType<typeof createClient<paths>> | null = null;

export function getApiClient(): ReturnType<typeof createClient<paths>> {
  if (_client !== null) return _client;
  const client = createClient<paths>({
    baseUrl: getCofferBaseUrl(),
    headers: { "X-Coffer-Actor": "ui" },
  });
  // Read the token fresh on every request via middleware rather than
  // capturing it at client-creation time. A token that arrives after the
  // first request (e.g. injected post-mount, or set via setCofferToken) is
  // then picked up automatically — no resetApiClient() / page reload needed.
  client.use({
    onRequest({ request }) {
      request.headers.set("X-Coffer-Token", getCofferToken() ?? "");
      return request;
    },
  });
  _client = client;
  return _client;
}

/** Drop the memoised client (e.g. if the base URL changes). */
export function resetApiClient(): void {
  _client = null;
}
