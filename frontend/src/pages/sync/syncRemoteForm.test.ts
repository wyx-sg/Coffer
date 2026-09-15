// frontend/src/pages/sync/syncRemoteForm.test.ts
import { describe, expect, test } from "vitest";

import { isDirty, isGitRemoteUrl, validateRemote, type FormState } from "./syncRemoteForm";

const base: FormState = {
  url: "https://git.example.com/me/vault.git",
  branch: "main",
  credentialRef: "",
  includeCredentials: false,
  intervalSeconds: 3600,
};

describe("isGitRemoteUrl", () => {
  test.each([
    "https://github.com/me/vault.git",
    "http://git.internal/vault",
    "ssh://git@github.com/me/vault.git",
    "git://github.com/me/vault.git",
    "git@github.com:me/vault.git",
    "  git@gitlab.example.com:group/vault.git  ",
  ])("accepts %s", (url) => {
    expect(isGitRemoteUrl(url)).toBe(true);
  });

  test.each(["", "   ", "not a url", "ftp://example.com/vault", "file:///tmp/vault", "https://"])(
    "rejects %j",
    (url) => {
      expect(isGitRemoteUrl(url)).toBe(false);
    },
  );
});

describe("validateRemote", () => {
  test("a valid draft has no errors", () => {
    expect(validateRemote(base)).toEqual({});
  });

  test("flags the URL and an interval under a minute, each by field", () => {
    expect(validateRemote({ ...base, url: "nope", intervalSeconds: 59 })).toEqual({
      url: "url",
      interval: "interval",
    });
    expect(validateRemote({ ...base, intervalSeconds: 60 })).toEqual({});
    expect(validateRemote({ ...base, intervalSeconds: Number.NaN })).toEqual({
      interval: "interval",
    });
  });
});

describe("isDirty", () => {
  test("ignores surrounding whitespace in text fields", () => {
    expect(isDirty({ ...base, url: `  ${base.url}  ` }, base)).toBe(false);
  });

  test("any real difference counts", () => {
    expect(isDirty({ ...base, includeCredentials: true }, base)).toBe(true);
    expect(isDirty({ ...base, intervalSeconds: 120 }, base)).toBe(true);
    expect(isDirty({ ...base, branch: "vault" }, base)).toBe(true);
  });
});
