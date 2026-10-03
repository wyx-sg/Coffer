<script setup lang="ts">
import { computed } from "vue";
import { useData, withBase } from "vitepress";

// Phone drawer, bottom row: language, theme, GitHub.
const { isDark, site, page } = useData();
const route = { get path() { return '/' + page.value.relativePath.replace(/(index)?\.md$/, ''); } };
const zh = computed(() => route.path.startsWith("/zh/") || route.path === "/zh");
const other = computed(() =>
  withBase(zh.value ? route.path.replace(/^\/zh/, "") || "/" : "/zh" + route.path),
);
const gh = computed(
  () => (site.value.themeConfig.socialLinks?.[0]?.link as string | undefined) ?? "https://github.com/wyx-sg/Coffer",
);
</script>

<template>
  <div class="coffer-drawer-foot">
    <a :href="other" class="lang">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m5 8 6 6M4 14l6-6 2-3M2 5h12M7 2h1M22 22l-5-10-5 10M14 18h6" /></svg>
      {{ zh ? "English" : "简体中文" }}
    </a>
    <span class="icons">
      <button type="button" :aria-label="zh ? '切换主题' : 'Toggle theme'" @click="isDark = !isDark">
        <svg v-if="!isDark" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z" /></svg>
        <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
      </button>
      <a :href="gh" aria-label="GitHub" target="_blank" rel="noopener">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A11.5 11.5 0 0 0 12 .5z" /></svg>
      </a>
    </span>
  </div>
</template>

<style scoped>
.coffer-drawer-foot {
  position: sticky;
  bottom: 0;
  margin-top: auto;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 8px 0 16px;
  border-top: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg-sidebar);
  font-size: 14px;
  color: var(--vp-c-text-1);
}
.lang {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--vp-c-text-1);
}
.lang svg,
.icons svg {
  color: var(--vp-c-text-2);
}
.icons {
  display: inline-flex;
}
.icons button,
.icons a {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
