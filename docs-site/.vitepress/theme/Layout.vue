<script setup lang="ts">
import DefaultTheme from "vitepress/theme";
import { onMounted, onBeforeUnmount } from "vue";
import DocCrumbs from "./components/site/DocCrumbs.vue";
import NotFound from "./components/site/NotFound.vue";
import DrawerHead from "./components/site/DrawerHead.vue";
import DrawerFoot from "./components/site/DrawerFoot.vue";

const { Layout } = DefaultTheme;

// On a phone the top-right menu button opens the page's own sidebar drawer
// (section select, grouped pages, language/theme/GitHub) instead of the stock
// nav screen. Pages without a sidebar keep the stock screen.
function redirect(e: Event) {
  const burger = (e.target as HTMLElement).closest(".VPNavBarHamburger");
  const menu = document.querySelector<HTMLElement>(".VPLocalNav button.menu");
  if (!burger || !menu) return;
  e.stopPropagation();
  e.preventDefault();
  menu.click();
}
onMounted(() => document.addEventListener("click", redirect, true));
onBeforeUnmount(() => document.removeEventListener("click", redirect, true));
</script>

<template>
  <Layout>
    <template #doc-before><DocCrumbs /></template>
    <template #not-found><NotFound /></template>
    <template #sidebar-nav-before><DrawerHead /></template>
    <template #sidebar-nav-after><DrawerFoot /></template>
  </Layout>
</template>
