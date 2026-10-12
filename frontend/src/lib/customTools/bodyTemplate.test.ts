import { describe, expect, it } from "vitest";

import {
  bodyTemplateProblem,
  bodyTemplateShown,
  fillBodyTemplate,
  formatBodyTemplate,
} from "./bodyTemplate";

const ONE_LINE =
  '{"userid_list":{userid_list},"region":{region},"note":"id {id}","query_flag":12345678901234567890,"empty":{},"tags":[]}';

describe("formatBodyTemplate", () => {
  it("lays out a template whose holes sit outside strings, keeping every token as written", () => {
    expect(formatBodyTemplate(ONE_LINE)).toBe(
      [
        "{",
        '  "userid_list": {userid_list},',
        '  "region": {region},',
        '  "note": "id {id}",',
        '  "query_flag": 12345678901234567890,',
        '  "empty": {},',
        '  "tags": []',
        "}",
      ].join("\n"),
    );
  });

  it("nests arrays and objects", () => {
    expect(formatBodyTemplate('{"a":[{"b":{env:X}},2]}')).toBe(
      ["{", '  "a": [', "    {", '      "b": {env:X}', "    },", "    2", "  ]", "}"].join("\n"),
    );
  });

  it("leaves a template that is not JSON alone", () => {
    expect(formatBodyTemplate('{"a":}')).toBeNull();
    expect(formatBodyTemplate("")).toBeNull();
  });

  it("keeps escaped quotes inside strings", () => {
    expect(formatBodyTemplate('{"a":"say \\"hi\\" {x}"}')).toBe('{\n  "a": "say \\"hi\\" {x}"\n}');
  });
});

describe("bodyTemplateProblem", () => {
  it("accepts holes outside strings", () => {
    expect(bodyTemplateProblem(ONE_LINE)).toBeNull();
  });

  it("names the line where the JSON breaks", () => {
    const problem = bodyTemplateProblem('{\n  "a": 1,\n  "b": \n}');
    expect(problem?.line).toBe(4);
  });
});

describe("bodyTemplateShown", () => {
  it("lays out a one-line template and keeps one written over several lines", () => {
    expect(bodyTemplateShown('{"a":{a}}')).toBe('{\n  "a": {a}\n}');
    expect(bodyTemplateShown('{"a":\n{a}}')).toBe('{"a":\n{a}}');
  });
});

describe("fillBodyTemplate", () => {
  it("fills holes the gateway's way: an input without a value is null, or nothing inside a string", () => {
    expect(
      fillBodyTemplate(
        '{"ids":{ids},"region":{region},"q":"id {id}","c":{env:cluster},"x":{missing},"y":"a{missing}b","z":{env:NOPE}}',
        { ids: ["1", "2"], region: "SG", id: 'a"b' },
        { cluster: '"sg2"' },
      ),
    ).toBe(
      [
        "{",
        '  "ids": [',
        '    "1",',
        '    "2"',
        "  ],",
        '  "region": "SG",',
        '  "q": "id a\\"b",',
        '  "c": "sg2",',
        '  "x": null,',
        '  "y": "ab",',
        '  "z": {env:NOPE}',
        "}",
      ].join("\n"),
    );
  });
});
