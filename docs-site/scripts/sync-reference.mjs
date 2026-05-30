import { fileURLToPath } from "node:url";
import { dirname, resolve, join, posix, basename } from "node:path";
import {
  readdirSync,
  statSync,
  mkdirSync,
  copyFileSync,
  readFileSync,
  writeFileSync,
  rmSync,
} from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = resolve(__dirname, "..", "..");
export const GH_BLOB = "https://github.com/wyx-sg/Coffer/blob/main";
const GH_TREE = GH_BLOB.replace("/blob/", "/tree/");
// Raw bytes endpoint — `blob` URLs serve an HTML page, so images embedded
// from repo assets must point at `/raw/` to actually render.
const GH_RAW = GH_BLOB.replace("/blob/", "/raw/");

// Returns true if the path segment looks like a directory (no file extension in
// the last segment, or ends with a "/").
function isDirectoryLike(p) {
  if (p.endsWith("/")) return true;
  const last = p.slice(p.lastIndexOf("/") + 1);
  return !last.includes(".");
}

// repo-relative source dir -> reference area slug
const AREAS = [
  { src: "specs", area: "specs" },
  { src: "docs/decisions", area: "adr" },
  { src: ".specify/memory", area: "project" },
  { src: "agents", area: "conventions" },
];
const EXCLUDED = new Set(["tasks.md", "tasks.zh.md"]);

// Normalise a repo path to posix separators for matching/output.
const toPosix = (p) => p.split("\\").join("/");

// Which area (if any) owns this repo-relative path?
function areaOf(repoPath) {
  const p = toPosix(repoPath);
  for (const { src, area } of AREAS) {
    if (p === src || p.startsWith(src + "/"))
      return { src, area, rest: p.slice(src.length + 1) };
  }
  return null;
}

// Decide destination for a source file, or null if it should be skipped.
export function classifyFile(repoPath) {
  const p = toPosix(repoPath);
  if (!p.endsWith(".md")) return null;
  const base = p.slice(p.lastIndexOf("/") + 1);
  if (EXCLUDED.has(base)) return null;
  const a = areaOf(p);
  if (!a) return null;
  const isZh = p.endsWith(".zh.md");
  let restNoZh = isZh ? a.rest.replace(/\.zh\.md$/, ".md") : a.rest;
  restNoZh = restNoZh.replace(/(^|\/)README\.md$/, "$1index.md"); // dir index → index.md
  return isZh
    ? { locale: "zh", dest: posix.join("zh/reference", a.area, restNoZh) }
    : { locale: "en", dest: posix.join("reference", a.area, restNoZh) };
}

// Map a repo-relative .md target to its on-site route (extensionless), or null.
function routeForTarget(repoPath) {
  const c = classifyFile(repoPath);
  if (!c) return null;
  return "/" + c.dest.replace(/\.md$/, "").replace(/\/index$/, "/");
}

// Rewrite markdown links/images in `content` whose source file is
// `srcRepoPath`. Matches both `[text](target)` and image `![alt](target)`;
// the leading `!` is captured so images are handled correctly (a GitHub
// `blob` URL serves HTML, not image bytes, so an image must use `/raw/`).
// The target may carry a `"title"` and/or surrounding whitespace
// (`](url "Title")`, `](url )`) — both standard markdown — so the URL is
// split out and the title preserved verbatim.
//
// Known, accepted limitations of this regex (not a full CommonMark parser;
// none occur in the synced corpus, which is enforced by the docs build):
//   - a title containing a literal `)` is truncated at the first `)`;
//   - a nested image-in-link `[![alt](img)](href)` rewrites only the inner
//     image, not the outer href.
// Per CommonMark an unbracketed destination cannot contain spaces, so
// splitting on the first whitespace to find the title is correct.
export function rewriteLinks(content, srcRepoPath) {
  const srcDir = posix.dirname(toPosix(srcRepoPath));
  return content.replace(
    /(!?)\[([^\]]*)\]\(([^)]+)\)/g,
    (whole, bang, text, rawTarget) => {
      // Separate the URL from an optional title; trim surrounding whitespace.
      const trimmed = rawTarget.trim();
      const wsIdx = trimmed.search(/\s/);
      const urlPart = wsIdx === -1 ? trimmed : trimmed.slice(0, wsIdx);
      const title = wsIdx === -1 ? "" : " " + trimmed.slice(wsIdx + 1).trim();
      const [path, ...rest] = urlPart.split("#");
      const hash = rest.length ? "#" + rest.join("#") : "";
      // external / anchor / already-rooted → unchanged
      if (path === "" || /^(https?:|mailto:|\/)/.test(path)) return whole;
      const repoTarget = toPosix(posix.normalize(posix.join(srcDir, path)));
      // A relative path that escapes the repo root can't be mapped sensibly —
      // leave it untouched rather than emit a broken `.../main/../..` URL.
      if (repoTarget.startsWith("../")) return whole;
      if (bang === "!") {
        // Image: repo asset → raw bytes URL so it renders on the site.
        const cleanTarget = repoTarget.replace(/\/+$/, "");
        return `![${text}](${GH_RAW}/${cleanTarget}${hash}${title})`;
      }
      if (repoTarget.endsWith(".md")) {
        const route = routeForTarget(repoTarget);
        if (route) return `[${text}](${route}${hash}${title})`;
      }
      const ghBase = isDirectoryLike(repoTarget) ? GH_TREE : GH_BLOB;
      const cleanTarget = repoTarget.replace(/\/+$/, "");
      return `[${text}](${ghBase}/${cleanTarget}${hash}${title})`; // non-synced or non-md → GitHub
    },
  );
}

// ---- pure helpers (exported for unit tests) ----

/**
 * Return the text of the first ATX `# ` heading in `markdown`, trimmed, with
 * surrounding backticks/asterisks stripped; return null if none found.
 * Skips YAML frontmatter (--- … ---) if present.
 */
export function extractTitle(markdown) {
  let text = markdown;
  // Strip YAML frontmatter
  if (text.startsWith("---")) {
    const end = text.indexOf("\n---", 3);
    if (end !== -1) {
      text = text.slice(end + 4); // skip past the closing ---
    }
  }
  for (const line of text.split("\n")) {
    if (/^# /.test(line)) {
      return line
        .slice(2)
        .trim()
        .replace(/^[`*]+|[`*]+$/g, "");
    }
  }
  return null;
}

// Known acronyms to UPPER-CASE when building spec folder labels
const ACRONYMS = {
  mcp: "MCP",
  ui: "UI",
  api: "API",
  cli: "CLI",
  adr: "ADR",
  sdd: "SDD",
};

/**
 * Turn a spec folder name into a nav label.
 * '001-mcp-gateway' → '001 · MCP Gateway'
 * If the first segment is not numeric, title-case all words joined by space.
 */
export function specFolderLabel(folder) {
  const parts = folder.split("-");
  if (/^\d+$/.test(parts[0])) {
    const num = parts[0];
    const words = parts.slice(1).map((w) => {
      const lo = w.toLowerCase();
      return ACRONYMS[lo] ?? lo.charAt(0).toUpperCase() + lo.slice(1);
    });
    return `${num} · ${words.join(" ")}`;
  }
  // Non-numeric first segment: title-case all words
  return parts
    .map((w) => {
      const lo = w.toLowerCase();
      return ACRONYMS[lo] ?? lo.charAt(0).toUpperCase() + lo.slice(1);
    })
    .join(" ");
}

// Category labels per locale
const CAT_LABELS = {
  en: {
    specs: "Specs",
    adr: "ADRs",
    project: "Project memory",
    conventions: "Engineering conventions",
  },
  zh: {
    specs: "规格",
    adr: "ADRs",
    project: "项目纲领",
    conventions: "工程规范",
  },
};

// File priority order within a spec folder
const SPEC_FILE_PRIORITY = [
  "spec",
  "plan",
  "data-model",
  "research",
  "quickstart",
];

// Uniform labels for spec sub-files, by base name, per locale. The spec NUMBER
// lives only on the parent group label (e.g. "001 · MCP Gateway"); the
// sub-files are labelled by document type so they read consistently regardless
// of how each source file's H1 happens to be worded.
const SPEC_FILE_LABELS = {
  en: {
    spec: "Spec",
    plan: "Plan",
    "data-model": "Data model",
    research: "Research",
    quickstart: "Quickstart",
    index: "Overview",
  },
  zh: {
    spec: "功能规格",
    plan: "实施计划",
    "data-model": "数据模型",
    research: "研究",
    quickstart: "快速上手",
    index: "概览",
  },
};

/**
 * Label for a spec sub-file (by base name + locale). Falls back to a titleized
 * base name (never the spec number, which belongs on the group label).
 */
export function specFileLabel(base, locale) {
  const known = SPEC_FILE_LABELS[locale]?.[base];
  if (known) return known;
  return base
    .split(/[-_]/)
    .map((w) => {
      const lo = w.toLowerCase();
      return ACRONYMS[lo] ?? lo.charAt(0).toUpperCase() + lo.slice(1);
    })
    .join(" ");
}

/**
 * Build the reference sidebar array for a given locale from an array of
 * file descriptors: { locale, area, route, base, specFolder? }
 */
function buildReferenceSidebar(descriptors, locale) {
  const labels = CAT_LABELS[locale];
  const prefix = locale === "zh" ? "/zh" : "";
  const byArea = { specs: [], adr: [], project: [], conventions: [] };
  for (const d of descriptors) {
    if (byArea[d.area]) byArea[d.area].push(d);
  }

  // ---- Specs group ----
  const specsByFolder = new Map();
  for (const d of byArea.specs) {
    const folder = d.specFolder ?? "unknown";
    if (!specsByFolder.has(folder)) specsByFolder.set(folder, []);
    specsByFolder.get(folder).push(d);
  }
  const sortedFolders = [...specsByFolder.keys()].sort();
  const specsItems = sortedFolders.map((folder) => {
    const files = specsByFolder.get(folder);
    files.sort((a, b) => {
      const ai = SPEC_FILE_PRIORITY.indexOf(a.base);
      const bi = SPEC_FILE_PRIORITY.indexOf(b.base);
      const aIdx = ai === -1 ? 999 : ai;
      const bIdx = bi === -1 ? 999 : bi;
      if (aIdx !== bIdx) return aIdx - bIdx;
      return a.base.localeCompare(b.base);
    });
    return {
      text: specFolderLabel(folder),
      collapsed: true,
      items: files.map((f) => ({
        text: specFileLabel(f.base, locale),
        link: f.route,
      })),
    };
  });

  // ---- ADRs group ----
  const adrFiles = byArea.adr.slice().sort((a, b) => {
    if (a.base === "index") return -1;
    if (b.base === "index") return 1;
    return a.base.localeCompare(b.base);
  });
  const adrItems = adrFiles.map((f) => ({ text: f.title, link: f.route }));

  // ---- Project group ----
  const projectOrder = ["constitution", "roadmap", "architecture"];
  const projectFiles = byArea.project.slice().sort((a, b) => {
    const ai = projectOrder.indexOf(a.base);
    const bi = projectOrder.indexOf(b.base);
    const aIdx = ai === -1 ? 999 : ai;
    const bIdx = bi === -1 ? 999 : bi;
    if (aIdx !== bIdx) return aIdx - bIdx;
    return a.base.localeCompare(b.base);
  });
  const projectItems = projectFiles.map((f) => ({
    text: f.title,
    link: f.route,
  }));

  // ---- Conventions group ----
  const convFiles = byArea.conventions
    .slice()
    .sort((a, b) => a.route.localeCompare(b.route));
  const convItems = convFiles.map((f) => ({ text: f.title, link: f.route }));

  return [
    { text: labels.specs, items: specsItems },
    { text: labels.adr, collapsed: true, items: adrItems },
    { text: labels.project, items: projectItems },
    { text: labels.conventions, items: convItems },
  ];
}

// ---- side-effecting build step (not imported by tests) ----
function walk(absDir, repoDir, out = []) {
  for (const name of readdirSync(absDir)) {
    const abs = join(absDir, name);
    const rep = posix.join(repoDir, name);
    if (statSync(abs).isDirectory()) walk(abs, rep, out);
    else out.push(rep);
  }
  return out;
}

function run() {
  for (const dir of ["reference", "zh/reference"]) {
    rmSync(resolve(__dirname, "..", dir), { recursive: true, force: true });
  }
  const seenEn = new Set();
  const seenZh = new Set();
  // descriptors collected for sidebar generation
  const descriptors = [];

  for (const { src, area } of AREAS) {
    const absSrc = resolve(REPO_ROOT, src);
    try {
      statSync(absSrc);
    } catch {
      continue;
    }
    for (const repoPath of walk(absSrc, src)) {
      const c = classifyFile(repoPath);
      if (!c) continue;
      const rawContent = readFileSync(resolve(REPO_ROOT, repoPath), "utf8");
      const content = rewriteLinks(rawContent, repoPath);
      const destAbs = resolve(__dirname, "..", c.dest);
      mkdirSync(dirname(destAbs), { recursive: true });
      writeFileSync(destAbs, content);
      (c.locale === "zh" ? seenZh : seenEn).add(c.dest.replace(/^zh\//, ""));

      // Build descriptor for sidebar
      const routeRaw =
        "/" + c.dest.replace(/\.md$/, "").replace(/\/index$/, "/");
      const baseNoExt = posix.basename(c.dest, ".md");
      // specFolder: for specs area, the path segment immediately after reference/specs/ or zh/reference/specs/
      let specFolder;
      if (area === "specs") {
        const m = c.dest.match(/reference\/specs\/([^/]+)\//);
        specFolder = m ? m[1] : undefined;
      }
      const titleizedBase = baseNoExt
        .split(/[-_]/)
        .map((w) => {
          const lo = w.toLowerCase();
          return ACRONYMS[lo] ?? lo.charAt(0).toUpperCase() + lo.slice(1);
        })
        .join(" ");
      const title = extractTitle(rawContent) ?? titleizedBase;
      descriptors.push({
        locale: c.locale,
        area,
        route: routeRaw,
        base: baseNoExt,
        specFolder,
        title,
      });
    }
  }

  // Fallback: EN doc with no ZH sibling → copy EN into the zh tree, warn.
  // Also add a zh descriptor mirroring the en one.
  for (const enDest of seenEn) {
    if (!seenZh.has(enDest)) {
      const from = resolve(__dirname, "..", enDest);
      const to = resolve(__dirname, "..", "zh", enDest);
      mkdirSync(dirname(to), { recursive: true });
      copyFileSync(from, to);
      console.warn(`[sync] no zh translation, using EN fallback: ${enDest}`);
      // Add zh descriptor mirroring en
      const enDesc = descriptors.find(
        (d) =>
          d.locale === "en" &&
          "/" + enDest.replace(/\.md$/, "").replace(/\/index$/, "/") ===
            d.route,
      );
      if (enDesc) {
        descriptors.push({
          ...enDesc,
          locale: "zh",
          route: "/zh" + enDesc.route,
        });
      }
    }
  }

  // Build and write sidebar JSON
  const enDescs = descriptors.filter((d) => d.locale === "en");
  const zhDescs = descriptors.filter((d) => d.locale === "zh");
  const sidebarJson = {
    en: buildReferenceSidebar(enDescs, "en"),
    zh: buildReferenceSidebar(zhDescs, "zh"),
  };
  const sidebarPath = resolve(
    __dirname,
    "..",
    ".vitepress",
    "reference-sidebar.json",
  );
  writeFileSync(sidebarPath, JSON.stringify(sidebarJson, null, 2) + "\n");
  console.log("[sync] reference layer synced");
  console.log("[sync] reference-sidebar.json written");
}

// Run only when invoked directly (not when imported by the test file).
if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
)
  run();
