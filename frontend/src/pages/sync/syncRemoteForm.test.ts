// frontend/src/pages/sync/syncRemoteForm.test.ts
import { describe, expect, test } from "vitest";

import type { SyncRemote } from "@/lib/api/sync";
import {
  EMPTY_FORM,
  formFromRemote,
  isGitRemoteUrl,
  toRemoteInput,
  validateRemote,
  type FormState,
} from "./syncRemoteForm";

const stored: SyncRemote = {
  url: "https://git.example.com/me/vault.git",
  branch: "main",
  secret_ref: "secret/gitlab-token",
  include_secret: false,
  interval_seconds: 3600,
  enabled: true,
};
const base: FormState = formFromRemote(stored);

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

test("validateRemote flags only a URL that is not a git remote", () => {
  expect(validateRemote(base)).toEqual({});
  expect(validateRemote({ ...base, url: "nope" })).toEqual({ url: "url" });
});

describe("formFromRemote", () => {
  test("no remote opens on the defaults", () => {
    expect(formFromRemote(null)).toEqual(EMPTY_FORM);
    expect(EMPTY_FORM).toMatchObject({ branch: "main", intervalSeconds: 3600, enabled: true });
  });
});

describe("toRemoteInput", () => {
  test("trims, defaults the branch, and sends no secret for an empty pick", () => {
    const out = toRemoteInput({ ...base, url: `  ${base.url} `, branch: " ", secretRef: "" });
    expect(out).toMatchObject({ url: base.url, branch: "main", secret_ref: null });
  });

  test("Only when I press Sync now is enabled: false, the interval kept", () => {
    expect(toRemoteInput({ ...base, enabled: false })).toMatchObject({
      enabled: false,
      interval_seconds: 3600,
    });
  });
});
