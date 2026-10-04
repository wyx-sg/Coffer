<script setup lang="ts">
// Styles the Markdown list inside it as hairline-separated decisions; the text
// stays in the page. Write each item as
//   - **The decision.** Why it was made. [Page](/architecture/page)
// The bold lead is the decision, a trailing link names the page that argues it.
</script>

<template>
  <div class="decisions"><slot /></div>
</template>

<style scoped>
.decisions :deep(ul) {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
  border-top: 1px solid var(--vp-c-divider);
}
.decisions :deep(li) {
  margin: 0;
  padding: 16px 0;
  border-bottom: 1px solid var(--vp-c-divider);
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
}
.decisions :deep(li > strong:first-child) {
  display: block;
  margin-bottom: 4px;
  font-size: 15px;
  line-height: 24px;
  color: var(--vp-c-text-1);
}
.decisions :deep(li > a:last-child) {
  display: table;
  margin-top: 6px;
  font-weight: 500;
  text-decoration: none;
}
.decisions :deep(li > a:last-child)::after {
  content: " →";
}
.decisions :deep(li > a:last-child:hover) {
  text-decoration: underline;
}
</style>
