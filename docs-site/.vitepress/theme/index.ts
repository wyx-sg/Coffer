import type { Component } from "vue";
import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";
import Layout from "./Layout.vue";
import "./custom.css";

// Every component under ./components is registered globally under its file
// name, so a page can use <HowItWorks /> or <AzBar /> without an import.
const components = import.meta.glob<{ default: Component }>("./components/**/*.vue", {
  eager: true,
});

export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }) {
    for (const [path, mod] of Object.entries(components)) {
      const name = path.split("/").pop()!.replace(/\.vue$/, "");
      app.component(name, mod.default);
    }
  },
} satisfies Theme;
