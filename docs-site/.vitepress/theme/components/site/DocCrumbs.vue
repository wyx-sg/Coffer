<script setup lang="ts">
import { computed } from "vue";
import { useData } from "vitepress";

// "Section › Sidebar group" above the page title, derived from the nav and the
// sidebar so it never needs maintaining by hand.
const { theme, frontmatter, page } = useData();
const route = { get path() { return '/' + page.value.relativePath.replace(/(index)?\.md$/, ''); } };

const norm = (p: string) => decodeURI(p).replace(/(index)?(\.html)?$/, "").replace(/\/$/, "");

const crumbs = computed(() => {
  const path = norm(route.path);
  const out: string[] = [];
  const nav = (theme.value.nav ?? []) as { text: string; activeMatch?: string; link?: string }[];
  const section = nav.find((n) => n.activeMatch && new RegExp(n.activeMatch).test(route.path));
  if (section) out.push(section.text);
  const sidebar = theme.value.sidebar as Record<string, any[]> | undefined;
  if (sidebar) {
    const key = Object.keys(sidebar)
      .filter((k) => route.path.startsWith(k))
      .sort((a, b) => b.length - a.length)[0];
    const has = (items: any[] | undefined): boolean =>
      !!items?.some((i) => (i.link && norm(i.link) === path) || has(i.items));
    // The innermost entry that holds this page: the sidebar group, or a
    // collapsible item inside it such as the CLI index.
    let level = (key ? sidebar[key] : []).find((g) => has(g.items));
    let parent = level;
    while (level) {
      const inner = level.items?.find((i: any) => i.items && has(i.items));
      if (!inner) break;
      parent = level = inner;
    }
    if (parent?.text && parent.text !== out[0]) out.push(parent.text);
  }
  return out;
});
</script>

<template>
  <nav v-if="crumbs.length && frontmatter.layout !== 'home'" class="coffer-crumbs" aria-label="Breadcrumb">
    <template v-for="(c, i) in crumbs" :key="i">
      <svg v-if="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6" /></svg>
      <span>{{ c }}</span>
    </template>
  </nav>
</template>
