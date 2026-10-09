// src/lib/customTools/responseRules.ts — a group's (or one tool's) response rules as the editor holds them, and the
// light checks that mirror the backend's (domain/mcp/http_api_response.py). The server stays the authority.
import type { ResponseRule } from "@/lib/api/customTools";

export type RuleSource = ResponseRule["source"];
type MessageSource = "header" | "json";

export const MAX_RULES = 10;
const MAX_DIAGNOSTIC_HEADERS = 20;
const MAX_OK_VALUES = 20;
const MAX_VALUE_LENGTH = 200;

/** Headers that carry credentials or cookies: never named by a rule or as a diagnostic header. */
const REFUSED_HEADERS: readonly string[] = [
  "authorization",
  "proxy-authorization",
  "cookie",
  "set-cookie",
  "set-cookie2",
  "www-authenticate",
  "proxy-authenticate",
  "x-api-key",
  "api-key",
];

const HEADER_NAME = /^[A-Za-z0-9!#$%&'*+.^_`|~-]+$/;

/** A comma-separated list, trimmed, without empty entries. */
export function splitList(text: string): string[] {
  return text
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x !== "");
}

export function emptyRule(): ResponseRule {
  return { source: "header", name: "", ok_values: [], missing: "ok", message: null };
}

/** Why a header name cannot be used, or null. */
export function headerProblem(name: string): "name" | "refused" | "invalid" | null {
  const n = name.trim();
  if (n === "") return "name";
  if (!HEADER_NAME.test(n)) return "invalid";
  return REFUSED_HEADERS.includes(n.toLowerCase()) ? "refused" : null;
}

function pointerProblem(name: string): "name" | "pointer" | null {
  if (name.trim() === "") return "name";
  return name.startsWith("/") ? null : "pointer";
}

function nameProblem(source: MessageSource | RuleSource, name: string) {
  if (source === "status") return null;
  return source === "header" ? headerProblem(name) : pointerProblem(name);
}

export type RuleProblem =
  | "name"
  | "pointer"
  | "refused"
  | "invalid"
  | "noValues"
  | "status"
  | "long";

/** What is wrong with a rule's own name and values, or null. */
export function ruleProblem(rule: ResponseRule): RuleProblem | null {
  const named = nameProblem(rule.source, rule.name ?? "");
  if (named) return named;
  if (rule.ok_values.length === 0) return "noValues";
  if (rule.ok_values.length > MAX_OK_VALUES) return "long";
  if (rule.ok_values.some((v) => v.length > MAX_VALUE_LENGTH)) return "long";
  if (
    rule.source === "status" &&
    rule.ok_values.some((v) => !/^\d+$/.test(v) || +v < 100 || +v > 599)
  )
    return "status";
  return null;
}

/** What is wrong with where a rule reads its message, or null. */
export function messageProblem(rule: ResponseRule): RuleProblem | null {
  return rule.message ? nameProblem(rule.message.source, rule.message.name) : null;
}

export function rulesValid(rules: readonly ResponseRule[]): boolean {
  return rules.length <= MAX_RULES && rules.every((r) => !ruleProblem(r) && !messageProblem(r));
}

export function diagnosticHeadersProblem(
  names: readonly string[],
): "refused" | "invalid" | "many" | null {
  if (names.length > MAX_DIAGNOSTIC_HEADERS) return "many";
  for (const n of names) {
    const p = headerProblem(n);
    if (p === "refused" || p === "invalid") return p;
  }
  return null;
}

/** One rule on one line, like `header x-result-code ∈ OK · missing: success · message: header x-result-text`. */
export function describeRule(rule: ResponseRule): string {
  const what = rule.source === "status" ? "status" : `${rule.source} ${rule.name ?? ""}`;
  const parts = [`${what} ∈ ${rule.ok_values.join(", ")}`];
  if (rule.source !== "status")
    parts.push(`missing: ${rule.missing === "error" ? "failure" : "success"}`);
  if (rule.message) parts.push(`message: ${rule.message.source} ${rule.message.name}`);
  return parts.join(" · ");
}
