<script setup lang="ts">
import { withBase } from "vitepress";

// items: { title, desc?, link, mono? }. variant "list" (default) is a bordered
// row list; "cards" is a grid of small bordered cards.
withDefaults(
  defineProps<{
    items: { title: string; desc?: string; link: string; mono?: boolean }[];
    variant?: "list" | "cards";
  }>(),
  { variant: "list" },
);
</script>

<template>
  <ul v-if="variant === 'list'" class="ll">
    <li v-for="i in items" :key="i.link">
      <a :href="withBase(i.link)">
        <span class="t" :class="{ mono: i.mono }">{{ i.title }}</span>
        <span class="d">{{ i.desc }}</span>
        <svg class="chev" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5 10.5 8 6 12.5" /></svg>
      </a>
    </li>
  </ul>
  <div v-else class="cards">
    <a v-for="i in items" :key="i.link" class="card" :href="withBase(i.link)">
      <span class="t">{{ i.title }}</span>
      <span class="d">{{ i.desc }}</span>
    </a>
  </div>
</template>

<style scoped>
.ll {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  overflow: hidden;
}
.ll li {
  margin: 0;
  border-top: 1px solid var(--vp-c-divider);
}
.ll li:first-child {
  border-top: 0;
}
.ll a {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  text-decoration: none;
  color: inherit;
}
.ll a:hover {
  background: var(--vp-c-bg-soft);
}
.t {
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.t.mono {
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
}
.d {
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
}
.chev {
  color: var(--vp-c-text-3);
}
.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  text-decoration: none;
}
.card:hover {
  background: var(--vp-c-bg-soft);
}
@media (max-width: 640px) {
  .ll a {
    grid-template-columns: minmax(0, 1fr) 16px;
    gap: 2px 12px;
  }
  .ll .d {
    grid-column: 1;
    grid-row: 2;
  }
  .ll .chev {
    grid-column: 2;
    grid-row: 1 / span 2;
  }
  .cards {
    grid-template-columns: 1fr;
  }
}
</style>
