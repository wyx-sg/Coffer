<script setup lang="ts">
// Styles the Markdown list inside it; the text stays in the page, so it is
// searchable, link-checked and translated with the page.
//   variant "list" (default): a bordered row list. Write each item as
//     - [Agents](/guides/agents) Register Claude Code and Codex…
//     The leading link is the row's title, and the whole row is clickable.
//   variant "cards": a grid of small bordered cards. Write each item as
//     - **Add Codex.** Run `coffer agent add codex`… See [Agents](/guides/agents).
withDefaults(defineProps<{ variant?: "list" | "cards" }>(), { variant: "list" });
</script>

<template>
  <div :class="variant === 'cards' ? 'cards' : 'll'"><slot /></div>
</template>

<style scoped>
.ll :deep(ul),
.cards :deep(ul) {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
}
.ll :deep(ul) {
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  overflow: hidden;
}
.ll :deep(li) {
  position: relative;
  margin: 0;
  padding: 14px 48px 14px 262px;
  border-top: 1px solid var(--vp-c-divider);
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
}
.ll :deep(li:first-child) {
  border-top: 0;
}
.ll :deep(li:hover) {
  background: var(--vp-c-bg-soft);
}
.ll :deep(li > a:first-child) {
  float: left;
  width: 230px;
  margin-left: -246px;
  font-size: 15px;
  font-weight: 600;
  color: var(--vp-c-text-1);
  text-decoration: none;
}
/* the title link stretches over the row; the row draws a chevron */
.ll :deep(li > a:first-child)::after {
  content: "";
  position: absolute;
  inset: 0;
}
.ll :deep(li)::after {
  content: "";
  position: absolute;
  right: 18px;
  top: 50%;
  width: 7px;
  height: 7px;
  margin-top: -4px;
  border-top: 1.5px solid var(--vp-c-text-3);
  border-right: 1.5px solid var(--vp-c-text-3);
  transform: rotate(45deg);
  pointer-events: none;
}
.ll :deep(li > a:first-child code) {
  padding: 0;
  background: none;
  font-size: 14px;
  color: inherit;
}
.cards :deep(ul) {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.cards :deep(li) {
  margin: 0;
  padding: 14px 16px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
}
.cards :deep(li > strong:first-child) {
  display: block;
  margin-bottom: 4px;
  font-size: 15px;
  color: var(--vp-c-text-1);
}
@media (max-width: 640px) {
  .ll :deep(li) {
    padding-left: 16px;
  }
  .ll :deep(li > a:first-child) {
    float: none;
    display: block;
    width: auto;
    margin-left: 0;
  }
  .cards :deep(ul) {
    grid-template-columns: 1fr;
  }
}
</style>
