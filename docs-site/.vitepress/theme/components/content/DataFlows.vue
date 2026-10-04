<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

// Wraps Markdown written as one `###` heading per flow, each followed by an
// ordered list whose items open with a bold actor: **Agent.** The agent calls…
// The text stays in the page (searchable, link-checked, translated with it);
// this component only turns the headings into a segmented control and shows
// one flow at a time. Without JavaScript every flow shows, one after another.
const root = ref<HTMLElement>();
const tabs = ref<{ id: string; text: string }[]>([]);
const active = ref(0);

function headings(): HTMLElement[] {
  return Array.from(root.value?.querySelectorAll<HTMLElement>(":scope > .body > h3") ?? []);
}

function apply() {
  let index = -1;
  for (const el of Array.from(root.value?.querySelector(".body")?.children ?? []) as HTMLElement[]) {
    if (el.tagName === "H3") index++;
    // the heading stays in the DOM for the outline and its anchor, but the
    // segmented control stands in for it on screen
    el.classList.toggle("flow-off", el.tagName === "H3" || index !== active.value);
  }
}

function select(i: number) {
  active.value = i;
  apply();
}

function fromHash() {
  const id = decodeURIComponent(location.hash.slice(1));
  const i = tabs.value.findIndex((t) => t.id === id);
  if (i < 0) return;
  select(i);
  root.value?.scrollIntoView({ block: "start" });
}

onMounted(() => {
  tabs.value = headings().map((h) => {
    const copy = h.cloneNode(true) as HTMLElement;
    copy.querySelector(".header-anchor")?.remove();
    return { id: h.id, text: (copy.textContent ?? "").trim() };
  });
  apply();
  fromHash();
  window.addEventListener("hashchange", fromHash);
});
onBeforeUnmount(() => window.removeEventListener("hashchange", fromHash));
</script>

<template>
  <div ref="root" class="flows">
    <div v-if="tabs.length" class="seg" role="tablist">
      <button
        v-for="(t, i) in tabs"
        :key="t.id"
        type="button"
        role="tab"
        :aria-selected="active === i"
        :class="{ on: active === i }"
        @click="select(i)"
      >
        {{ t.text }}
      </button>
    </div>
    <div class="body"><slot /></div>
  </div>
</template>

<style scoped>
.flows {
  margin-top: 16px;
}
.seg {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 3px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
}
.seg button {
  font: inherit;
  font-size: 13px;
  line-height: 20px;
  padding: 3px 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--vp-c-text-2);
  cursor: pointer;
}
.seg button.on {
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-weight: 600;
  box-shadow: 0 0 0 1px var(--vp-c-divider);
}
.body :deep(.flow-off) {
  display: none;
}
.body :deep(ol) {
  list-style: none;
  counter-reset: flow;
  margin: 12px 0 0;
  padding: 0;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  overflow: hidden;
}
.body :deep(ol > li) {
  counter-increment: flow;
  position: relative;
  margin: 0;
  padding: 12px 16px 12px 206px;
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
  border-top: 1px solid var(--vp-c-divider);
}
.body :deep(ol > li:first-child) {
  border-top: 0;
}
.body :deep(ol > li)::before {
  content: counter(flow);
  position: absolute;
  left: 16px;
  top: 12px;
  color: var(--vp-c-text-3);
}
.body :deep(ol > li > strong:first-child) {
  position: absolute;
  left: 44px;
  top: 12px;
  width: 150px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.body :deep(ol > li code) {
  font-size: 13px;
}
@media (max-width: 640px) {
  .body :deep(ol > li) {
    padding-left: 44px;
  }
  .body :deep(ol > li > strong:first-child) {
    position: static;
    display: block;
    width: auto;
  }
}
</style>
