<script setup lang="ts">
import { computed } from "vue";
import { useData, withBase } from "vitepress";

const { lang } = useData();
const zh = computed(() => lang.value.startsWith("zh"));
const p = computed(() => (zh.value ? "/zh" : ""));

const t = computed(() =>
  zh.value
    ? {
        title: "页面不存在",
        lead: "这个页面不存在，或者在文档重新整理时被移走了。搜一搜，或者从下面这些入口开始。",
        search: "搜索文档",
        home: "回到首页",
        cards: [
          ["开始使用", "安装，然后连接第一个智能体。", "/start/"],
          ["指南", "一个任务一页。", "/guides/"],
          ["CLI 参考", "每条命令和选项。", "/reference/cli"],
        ],
      }
    : {
        title: "Page not found",
        lead: "This page does not exist, or it moved when the docs were reorganized. Search for it, or start from one of these.",
        search: "Search the docs",
        home: "Go to the home page",
        cards: [
          ["Get started", "Install, then connect your first agent.", "/start/"],
          ["Guides", "One page per task.", "/guides/"],
          ["CLI reference", "Every command and option.", "/reference/cli"],
        ],
      },
);

function openSearch() {
  const btn = document.querySelector<HTMLElement>(".VPNavBarSearch button");
  if (btn) return btn.click();
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
}
</script>

<template>
  <div class="coffer-404">
    <span class="code">404</span>
    <h1>{{ t.title }}</h1>
    <p class="lead">{{ t.lead }}</p>
    <div class="actions">
      <button type="button" class="btn primary" @click="openSearch">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        {{ t.search }}
      </button>
      <a class="btn" :href="withBase(p + '/')">{{ t.home }}</a>
    </div>
    <div class="cards">
      <a v-for="c in t.cards" :key="c[2]" class="card" :href="withBase(p + c[2])">
        <b>{{ c[0] }}</b><span>{{ c[1] }}</span>
      </a>
    </div>
  </div>
</template>
