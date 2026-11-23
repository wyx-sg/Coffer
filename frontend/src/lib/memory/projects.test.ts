import { describe, expect, it } from "vitest";
import { projectName } from "@/lib/memory/projects";

describe("projectName", () => {
  it("drops a git host prefix", () => {
    expect(projectName("github.com-acme-payments")).toBe("acme-payments");
    expect(projectName("git.garena.com-shopee-core-server-account")).toBe(
      "shopee-core-server-account",
    );
    expect(projectName("gitlab.com-acme-api")).toBe("acme-api");
    expect(projectName("bitbucket.org-acme-web")).toBe("acme-web");
  });

  it("keeps a folder that has no git host prefix", () => {
    expect(projectName("wyx-sg-Coffer")).toBe("wyx-sg-Coffer");
    expect(projectName("yuxing.wu-blackcat")).toBe("yuxing.wu-blackcat");
  });
});
