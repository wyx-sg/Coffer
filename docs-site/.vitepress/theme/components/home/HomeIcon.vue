<script setup lang="ts">
import { computed } from "vue";
import { ICONS } from "./homeStrings";

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 16 });
const path = computed(() => ICONS[props.name] ?? "");
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    style="flex-shrink: 0"
    v-html="path"
  />
</template>
