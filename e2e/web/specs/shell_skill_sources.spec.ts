// e2e/web/specs/shell_skill_sources.spec.ts
//
// skill-manager "Add skills from an archive" through the web UI: open /skills,
// Add skill → From an archive → upload a .zip built here, see the skill the
// dialog found, confirm, and find the skill on the page. Nothing is added
// before the confirm; the skill is removed over REST afterwards so the shared
// e2e DB stays clean.

import { expect, test } from "@playwright/test";
import {
  beforeEachInjectToken,
  readDaemonToken,
  resolveResourceUid,
} from "./_helpers";

beforeEachInjectToken();

// ---------------------------------------------------------------------------
// A minimal .zip writer: stored entries (no compression), which every zip
// reader accepts. Node ships no zip library, and a fixture file would hide
// what the archive holds.
// ---------------------------------------------------------------------------

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(data: Buffer): number {
  let c = 0xffffffff;
  for (const byte of data) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function storedZip(entries: Record<string, string>): Buffer {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const [name, text] of Object.entries(entries)) {
    const fileName = Buffer.from(name, "utf-8");
    const data = Buffer.from(text, "utf-8");
    const crc = crc32(data);

    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); // local file header signature
    local.writeUInt16LE(20, 4); // version needed to extract
    local.writeUInt16LE(0x0800, 6); // flags: UTF-8 names
    local.writeUInt16LE(0, 8); // method: stored
    local.writeUInt16LE(0, 10); // mod time
    local.writeUInt16LE(0x21, 12); // mod date (1980-01-01)
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18); // compressed size
    local.writeUInt32LE(data.length, 22); // uncompressed size
    local.writeUInt16LE(fileName.length, 26);
    local.writeUInt16LE(0, 28); // extra length
    locals.push(local, fileName, data);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); // central directory signature
    central.writeUInt16LE(20, 4); // version made by
    central.writeUInt16LE(20, 6); // version needed
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt16LE(0, 12);
    central.writeUInt16LE(0x21, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(fileName.length, 28);
    central.writeUInt16LE(0, 30); // extra length
    central.writeUInt16LE(0, 32); // comment length
    central.writeUInt16LE(0, 34); // disk number
    central.writeUInt16LE(0, 36); // internal attributes
    central.writeUInt32LE(0, 38); // external attributes (a regular file)
    central.writeUInt32LE(offset, 42); // local header offset
    centrals.push(central, fileName);

    offset += local.length + fileName.length + data.length;
  }
  const directory = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); // end of central directory signature
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  const count = Object.keys(entries).length;
  end.writeUInt16LE(count, 8);
  end.writeUInt16LE(count, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  end.writeUInt16LE(0, 20);
  return Buffer.concat([...locals, directory, end]);
}

test("an archive is added from the Add skill dialog only after it is confirmed", async ({
  page,
}) => {
  const { token, port } = readDaemonToken();
  const skillName = `e2e-archive-${Date.now().toString(36)}`;
  const description = `Added from an archive by the e2e suite (${skillName}).`;
  const archive = storedZip({
    "SKILL.md": `---\nname: ${skillName}\ndescription: ${description}\n---\n\nbody\n`,
    "references/notes.md": "notes\n",
  });

  try {
    await page.goto("/skills");
    await page.getByRole("button", { name: "Add skill" }).first().click();

    const dialog = page.getByRole("dialog", { name: "Add skill" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("radio")).toHaveText([
      "From a folder",
      "From an archive",
      "From Git",
    ]);
    await dialog.getByRole("radio", { name: "From an archive" }).click();
    await dialog.getByLabel("Archive").setInputFiles({
      name: `${skillName}.zip`,
      mimeType: "application/zip",
      buffer: archive,
    });

    // What the archive holds is shown, and nothing is registered yet.
    await expect(
      dialog.getByText("Found SKILL.md at the top level"),
    ).toBeVisible({
      timeout: 15_000,
    });
    await expect(dialog.getByText(skillName, { exact: true })).toBeVisible();
    await expect(dialog.getByText(description)).toBeVisible();
    expect(await resolveResourceUid("skill", skillName)).toBeNull();

    await dialog
      .getByRole("button", { name: "Add skill", exact: true })
      .click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    // The skill is registered and shown on the Skills page.
    await expect
      .poll(() => resolveResourceUid("skill", skillName), { timeout: 10_000 })
      .not.toBeNull();
    await expect(
      page.getByText(skillName, { exact: true }).first(),
    ).toBeVisible({
      timeout: 10_000,
    });
  } finally {
    const uid = await resolveResourceUid("skill", skillName);
    if (uid !== null) {
      try {
        await fetch(`http://127.0.0.1:${port}/api/v1/skills/${uid}`, {
          method: "DELETE",
          headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
        });
      } catch {
        // best-effort
      }
    }
  }
});
