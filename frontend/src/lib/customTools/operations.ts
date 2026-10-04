// src/lib/customTools/operations.ts — pure helpers over the operations an OpenAPI reading drafts.
import type { OpenApiReading } from "@/lib/api/customTools";
import { changesDataByDefault } from "@/lib/customTools/groups";

export type Operation = OpenApiReading["operations"][number];

/** The section an operation is listed under: its tag, else its path's first segment. */
export function sectionOf(op: Operation): string {
  if (op.tag) return op.tag;
  const first = op.tool.path.split("/").find((part) => part && !part.startsWith("{")) ?? "";
  const word = first.split("?")[0];
  return word ? word[0].toUpperCase() + word.slice(1) : "/";
}

/** Whether an operation's tool changes data: its flag, else its method's default. */
export function operationChangesData(op: Operation): boolean {
  return op.tool.changes_data ?? changesDataByDefault(op.tool.method ?? "GET");
}
