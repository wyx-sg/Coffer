<script setup lang="ts">
import { computed } from "vue";
import { useData, useRouter, withBase } from "vitepress";

// Phone drawer, top part: title, close, and the Section select.
const { theme, page } = useData();
const route = { get path() { return '/' + page.value.relativePath.replace(/(index)?\.md$/, ''); } };
const router = useRouter();

type NavItem = { text: string; link?: string; activeMatch?: string };
const sections = computed(() => ((theme.value.nav ?? []) as NavItem[]).filter((n) => n.link));
const current = computed(
  () => sections.value.find((n) => n.activeMatch && new RegExp(n.activeMatch).test(route.path))?.link ?? "",
);
const zh = computed(() => route.path.startsWith("/zh/") || route.path === "/zh");

function go(e: Event) {
  router.go(withBase((e.target as HTMLSelectElement).value));
}
function close() {
  document.querySelector<HTMLElement>(".VPBackdrop")?.click();
}
</script>

<template>
  <div class="coffer-drawer-head">
    <div class="bar">
      <span>{{ zh ? "菜单" : "Menu" }}</span>
      <button type="button" :aria-label="zh ? '关闭菜单' : 'Close menu'" @click="close">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg>
      </button>
    </div>
    <label class="select">
      <span>{{ zh ? "栏目" : "Section" }}</span>
      <select @change="go">
        <!-- :selected on each option, not :value on the select: server-rendered
             HTML only carries the selected attribute. -->
        <option v-for="s in sections" :key="s.link" :value="s.link" :selected="s.link === current">{{ s.text }}</option>
      </select>
    </label>
  </div>
</template>

<style scoped>
.coffer-drawer-head {
  flex-direction: column;
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--vp-c-bg-sidebar);
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 4px 0 16px;
  border-bottom: 1px solid var(--vp-c-border);
  font-size: 15px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.bar button {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--vp-c-text-2);
}
.select {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--vp-c-border);
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--vp-c-text-2);
}
select {
  height: 44px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg);
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
</style>
