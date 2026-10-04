// frontend/src/components/mcp/add/nameProblem.ts — why a new MCP server's name
// cannot be registered, as an i18n key under `mcp.add` plus its values, or null.
//
// Checked as the user types, before submit: the daemon would refuse each of
// these, and the name is fixed once registered, so the dialog says so under
// the field instead of sending a registration it knows will fail.
import { MCP_SERVER_NAME_MAX, isValidServerName, serverNameTooLong } from "@/lib/mcp/pasteParse";

export interface NameProblem {
  key: string;
  params: Record<string, string | number>;
}

/** `taken` holds the names already registered (and, in a review, the other
 *  names of the same batch). An empty name has no message — the submit button
 *  is simply off. */
export function nameProblem(name: string, taken: ReadonlySet<string>): NameProblem | null {
  if (name === "") return null;
  if (serverNameTooLong(name)) {
    return { key: "nameTooLong", params: { length: name.length, max: MCP_SERVER_NAME_MAX } };
  }
  if (!isValidServerName(name)) return { key: "nameInvalid", params: {} };
  if (taken.has(name)) return { key: "nameTaken", params: { name } };
  return null;
}

/** Whether `name` can be sent at all. */
export function nameSendable(name: string, taken: ReadonlySet<string>): boolean {
  return name !== "" && nameProblem(name, taken) === null;
}
