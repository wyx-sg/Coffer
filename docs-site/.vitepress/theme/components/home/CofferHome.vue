<script setup lang="ts">
import { withBase } from "vitepress";
import { computed } from "vue";
import { STR, type Lang } from "./homeStrings";

const props = defineProps<{ lang: Lang }>();
const s = computed(() => STR[props.lang]);
const href = (p: string) => withBase((props.lang === "zh" ? "/zh" : "") + p);
</script>

<template>
  <div class="coffer-home" :class="{ zh: lang === 'zh' }">
    <section class="hero">
      <div class="in">
        <div class="hero-grid">
          <div class="hero-copy">
            <h1>{{ s.h1 }}</h1>
            <p class="lead">{{ s.lead }}</p>
            <div class="btns">
              <a class="btn primary" :href="href('/start/')">
                {{ s.start }}<HomeIcon name="arrow" :size="16" />
              </a>
              <a class="btn" href="https://github.com/wyx-sg/Coffer" target="_blank" rel="noreferrer">
                <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M12 2C6.48 2 2 6.58 2 12.24c0 4.52 2.87 8.36 6.84 9.72.5.09.68-.22.68-.49l-.01-1.7c-2.78.62-3.37-1.37-3.37-1.37-.45-1.18-1.11-1.49-1.11-1.49-.91-.64.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.89 1.57 2.34 1.12 2.91.86.09-.66.35-1.12.63-1.37-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.04 1.03-2.76-.1-.26-.45-1.3.1-2.72 0 0 .84-.28 2.75 1.05A9.4 9.4 0 0 1 12 6.9c.85 0 1.7.12 2.5.35 1.9-1.33 2.74-1.05 2.74-1.05.55 1.42.2 2.46.1 2.72.64.72 1.03 1.64 1.03 2.76 0 3.94-2.34 4.8-4.57 5.06.36.32.68.94.68 1.9l-.01 2.82c0 .27.18.59.69.49A10.1 10.1 0 0 0 22 12.24C22 6.58 17.52 2 12 2z"
                  />
                </svg>
                GitHub
              </a>
            </div>
          </div>
          <InstallTabs :lang="lang" />
        </div>
        <HomeShots :lang="lang" />
      </div>
    </section>

    <FeatureGrid :lang="lang" />
    <HowItWorks :lang="lang" />
    <StartHere :lang="lang" />
  </div>
</template>

<style scoped>
.coffer-home {
  width: 100%;
  color: var(--vp-c-text-1);
  overflow-x: clip;
}
.in {
  width: min(1184px, calc(100% - 48px));
  margin: 0 auto;
}
.hero {
  padding: 88px 0 96px;
}
.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  column-gap: 64px;
  align-items: end;
}
.hero-copy {
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-width: 0;
}
h1 {
  margin: 0;
  padding: 0;
  border: 0;
  font-size: 56px;
  line-height: 62px;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--vp-c-text-1);
}
.zh h1 {
  font-size: 52px;
  line-height: 64px;
  letter-spacing: 0;
}
.lead {
  margin: 0;
  font-size: 18px;
  line-height: 30px;
  color: var(--vp-c-text-2);
}
.zh .lead {
  line-height: 32px;
}
.btns {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 44px;
  padding: 0 18px;
  box-sizing: border-box;
  border-radius: 8px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  border: 1px solid var(--vp-c-border);
  font-size: 15px;
  font-weight: 600;
  text-decoration: none;
}
.btn.primary {
  padding: 0 20px;
  background: var(--vp-button-brand-bg, var(--vp-c-brand-2));
  border-color: transparent;
  color: #fff;
}
.btn.primary:hover {
  background: var(--vp-button-brand-hover-bg, var(--vp-c-brand-1));
}
@media (max-width: 959px) {
  .hero {
    padding: 48px 0 56px;
  }
  .hero-grid {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 32px;
  }
}
@media (max-width: 639px) {
  h1 {
    font-size: 38px;
    line-height: 44px;
  }
  .zh h1 {
    font-size: 36px;
    line-height: 46px;
  }
  .lead {
    font-size: 16px;
    line-height: 26px;
  }
}
</style>
