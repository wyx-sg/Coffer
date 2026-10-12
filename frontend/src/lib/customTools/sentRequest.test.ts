import { describe, expect, it } from "vitest";

import { sentRequest } from "./sentRequest";

const preview = {
  url: "https://api.example.com/users/{id}?param={param}&ids={ids}&fixed=1",
  headers: [
    { name: "Accept", value: "application/json", secret: null, from: "environment" as const },
    { name: "shopee-baggage", value: "CID={cid}", secret: null, from: "tool" as const },
  ],
  missingVariables: [],
};

describe("sentRequest", () => {
  it("fills the URL, drops a query pair or tool header without a value, and repeats a list", () => {
    const sent = sentRequest(
      preview,
      { method: "GET", path: "/users/{id}?param={param}&ids={ids}&fixed=1" },
      { id: "a/b", ids: ["1", "2"] },
      {},
    );
    expect(sent.url).toBe("https://api.example.com/users/a%2Fb?ids=1&ids=2&fixed=1");
    expect(sent.headers.map((h) => h.name)).toEqual(["Accept"]);
    expect(sent.body).toBeNull();
    expect(sent.missingPath).toEqual([]);
  });

  it("keeps a path hole without a value and reports it", () => {
    const sent = sentRequest(preview, { method: "GET", path: "/users/{id}" }, {}, {});
    expect(sent.url).toBe("https://api.example.com/users/{id}?fixed=1");
    expect(sent.missingPath).toEqual(["id"]);
  });

  it("fills the body template and adds the JSON content type", () => {
    const sent = sentRequest(
      { url: "https://x/y", headers: [], missingVariables: [] },
      { method: "POST", path: "/y", body_template: '{"r":{region}}' },
      { region: "SG" },
      {},
    );
    expect(sent.body).toBe('{\n  "r": "SG"\n}');
    expect(sent.headers).toEqual([
      { name: "Content-Type", value: "application/json", secret: null, from: "tool" },
    ]);
  });

  it("sends the inputs used nowhere else as the body of a POST without a template", () => {
    const sent = sentRequest(
      { url: "https://x/y/{id}", headers: [], missingVariables: [] },
      { method: "POST", path: "/y/{id}" },
      { id: 1, name: "n" },
      {},
    );
    expect(sent.body).toBe('{\n  "name": "n"\n}');
  });
});
