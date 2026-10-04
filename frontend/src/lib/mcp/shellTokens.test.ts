import { describe, expect, test } from "vitest";
import { shellSplit } from "./shellTokens";

describe("shellSplit", () => {
  test.each([
    ["npx -y pkg", ["npx", "-y", "pkg"]],
    ["  a   b  ", ["a", "b"]],
    [`a 'b c' "d e"`, ["a", "b c", "d e"]],
    [`a "say \\"hi\\"" 'lit\\eral'`, ["a", 'say "hi"', "lit\\eral"]],
    ["a b\\ c", ["a", "b c"]],
    ["a \\\n  b", ["a", "b"]],
    [`-H "Authorization: Bearer x"`, ["-H", "Authorization: Bearer x"]],
    [`k=""`, ["k="]],
  ])("%j", (line, want) => {
    expect(shellSplit(line)).toEqual(want);
  });

  test("an open quote is null", () => {
    expect(shellSplit(`npx "unterminated`)).toBeNull();
    expect(shellSplit(`npx 'unterminated`)).toBeNull();
  });
});
