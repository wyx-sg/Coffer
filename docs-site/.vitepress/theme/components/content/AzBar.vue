<script setup lang="ts">
import { onMounted, ref } from "vue";

// Letters with an h2 single-letter heading on the page are links; others gray.
const props = defineProps<{ letters?: string[] }>();
const all = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const present = ref<Set<string>>(new Set(props.letters ?? []));

onMounted(() => {
  if (props.letters) return;
  const s = new Set<string>();
  document.querySelectorAll(".vp-doc h2").forEach((h) => {
    const t = (h.id || "").trim() || (h.textContent || "").replace(/[\s#​]/g, "");
    if (/^[A-Za-z]$/.test(t)) s.add(t.toUpperCase());
  });
  present.value = s;
});
</script>

<template>
  <nav class="az" aria-label="A to Z">
    <template v-for="l in all" :key="l">
      <a v-if="present.has(l)" :href="'#' + l.toLowerCase()" class="on">{{ l }}</a>
      <span v-else>{{ l }}</span>
    </template>
  </nav>
</template>

<style scoped>
.az {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  margin: 20px 0 0;
  padding: 8px 14px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  font-size: 14px;
  line-height: 22px;
  font-weight: 600;
}
.az a,
.az span {
  min-width: 18px;
  text-align: center;
  font-weight: 600;
  text-decoration: none;
}
.az a {
  color: var(--vp-c-brand-1);
}
.az span {
  color: var(--vp-c-text-3);
  opacity: 0.6;
}
</style>
