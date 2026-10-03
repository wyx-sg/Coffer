<script setup lang="ts">
import { withBase } from "vitepress";

// items: { title, why, link, linkText } — hairline-separated, no box.
defineProps<{ items: { title: string; why: string; link?: string; linkText?: string }[] }>();
</script>

<template>
  <ul class="decisions">
    <li v-for="d in items" :key="d.title">
      <div class="d-title">{{ d.title }}</div>
      <div class="d-why">{{ d.why }}</div>
      <a v-if="d.link" class="d-link" :href="withBase(d.link)">{{ d.linkText }} →</a>
    </li>
  </ul>
</template>

<style scoped>
.decisions {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
  border-top: 1px solid var(--vp-c-divider);
}
.decisions li {
  margin: 0;
  padding: 16px 0;
  border-bottom: 1px solid var(--vp-c-divider);
}
.d-title {
  font-size: 15px;
  line-height: 24px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.d-why {
  margin-top: 4px;
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
}
.d-link {
  display: inline-block;
  margin-top: 6px;
  font-size: 14px;
  line-height: 22px;
  font-weight: 500;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}
.d-link:hover {
  text-decoration: underline;
}
</style>
