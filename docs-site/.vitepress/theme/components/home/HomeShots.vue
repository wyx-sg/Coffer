<script setup lang="ts">
import { useData, withBase } from "vitepress";
import { computed, ref } from "vue";
import { STR, SHOT_IDS, type Lang } from "./homeStrings";

const props = defineProps<{ lang: Lang }>();
const s = computed(() => STR[props.lang]);
const { isDark } = useData();

const active = ref(0);
const tabs = computed(() => SHOT_IDS.map((id, i) => ({ id, ...s.value.shots[i] })));
const current = computed(() => tabs.value[active.value]);
const src = computed(
  () => withBase(`/shots/${props.lang}/${isDark.value ? "dark" : "light"}/home-${current.value.id}.webp`),
);

const buttons = ref<HTMLElement[]>([]);
function onKey(event: KeyboardEvent) {
  const last = tabs.value.length - 1;
  let next = active.value;
  if (event.key === "ArrowRight") next = active.value === last ? 0 : active.value + 1;
  else if (event.key === "ArrowLeft") next = active.value === 0 ? last : active.value - 1;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = last;
  else return;
  event.preventDefault();
  active.value = next;
  buttons.value[next]?.focus();
}
</script>

<template>
  <div class="home-shots">
    <div class="tabs" role="tablist" :aria-label="s.shotsLabel" @keydown="onKey">
      <button
        v-for="(tab, i) in tabs"
        :id="`shot-tab-${tab.id}`"
        :key="tab.id"
        :ref="(el) => (buttons[i] = el as HTMLElement)"
        class="tab"
        :class="{ on: i === active }"
        role="tab"
        type="button"
        :aria-selected="i === active"
        aria-controls="shot-panel"
        :tabindex="i === active ? 0 : -1"
        @click="active = i"
      >
        {{ tab.label }}
      </button>
    </div>
    <p class="caption">{{ current.text }}</p>
    <div id="shot-panel" class="window" role="tabpanel" :aria-labelledby="`shot-tab-${current.id}`">
      <img :key="src" :src="src" width="2880" height="1800" :alt="current.alt" decoding="async" />
      <div class="fade" aria-hidden="true" />
    </div>
  </div>
</template>

<style scoped>
.home-shots {
  margin-top: 56px;
}
.tabs {
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
}
.tab {
  flex: none;
  height: 36px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.tab:hover {
  color: var(--vp-c-text-1);
  background: var(--vp-c-bg-soft);
}
.tab.on {
  color: var(--vp-c-text-1);
  background: var(--vp-c-bg-soft);
  border-color: var(--vp-c-border);
}
.tab:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}
.caption {
  min-height: 24px;
  margin: 12px 0 16px;
  font-size: 15px;
  line-height: 24px;
  color: var(--vp-c-text-2);
}
.window {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg);
  box-shadow: 0 24px 48px -24px rgb(0 0 0 / 0.25);
}
.window img {
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 8 / 5;
}
.fade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 12%;
  background: linear-gradient(to bottom, transparent, var(--vp-c-bg));
  pointer-events: none;
}
@media (prefers-reduced-motion: no-preference) {
  .window img {
    animation: shot-in 0.2s ease-out;
  }
  @keyframes shot-in {
    from {
      opacity: 0.4;
    }
  }
}
</style>
