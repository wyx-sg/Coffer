<script setup lang="ts">
import { useData, withBase } from "vitepress";
import { computed } from "vue";
import manifest from "../../../../public/shots/manifest.json";

// A generated picture of the app (see `make docs-shots`), by name. Both themes
// are in the page and CSS shows the one the reader has on, so a theme switch
// never waits on a download.
const props = defineProps<{ name: string; alt: string }>();
const { localeIndex } = useData();

const lang = computed(() => (localeIndex.value === "zh" ? "zh" : "en"));
const url = (theme: "light" | "dark") => withBase(`/shots/${lang.value}/${theme}/${props.name}.webp`);
const size = computed(
  () => (manifest as Record<string, [number, number]>)[`${lang.value}/light/${props.name}`],
);
</script>

<template>
  <figure class="shot">
    <img
      class="light"
      :src="url('light')"
      :width="size?.[0]"
      :height="size?.[1]"
      :alt="alt"
      loading="lazy"
      decoding="async"
    />
    <img
      class="dark"
      :src="url('dark')"
      :width="size?.[0]"
      :height="size?.[1]"
      :alt="alt"
      loading="lazy"
      decoding="async"
    />
  </figure>
</template>

<style scoped>
.shot {
  margin: 20px 0;
}
.shot img {
  display: block;
  width: 100%;
  max-width: 760px;
  height: auto;
  border: 1px solid var(--vp-c-border);
  border-radius: 10px;
  box-shadow: 0 12px 28px -16px rgb(0 0 0 / 0.25);
}
.dark {
  display: none !important;
}
:global(html.dark) .shot .light {
  display: none !important;
}
:global(html.dark) .shot .dark {
  display: block !important;
}
</style>
