<script setup lang="ts">
import { withBase } from "vitepress";
import { computed } from "vue";
import { STR, type Lang } from "./homeStrings";

const props = defineProps<{ lang: Lang }>();
const s = computed(() => STR[props.lang]);
const href = (p: string) => withBase((props.lang === "zh" ? "/zh" : "") + p);
</script>

<template>
  <section class="path" aria-labelledby="start-here">
    <div class="in">
      <h2 id="start-here">{{ s.pathH }}</h2>
      <ol class="steps">
        <template v-for="(st, i) in s.path" :key="st[0]">
          <li v-if="i" class="chev" aria-hidden="true"><HomeIcon name="chev" :size="16" /></li>
          <li class="step">
            <a :href="href(st[2])">
              <span class="n">{{ i + 1 }}</span>
              <span class="t">{{ st[0] }}</span>
              <span class="d">{{ st[1] }}</span>
            </a>
          </li>
        </template>
      </ol>
      <p class="after">
        {{ s.after[0] }}<a :href="href('/guides/')">{{ s.after[1] }}</a>{{ s.after[2]
        }}<a :href="href('/reference/')">{{ s.after[3] }}</a>{{ s.after[4] }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.path {
  padding: 88px 0 96px;
}
.in {
  width: min(1184px, calc(100% - 48px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
h2 {
  margin: 0;
  padding: 0;
  border: 0;
  font-size: 32px;
  line-height: 40px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--vp-c-text-1);
}
:global(.zh) h2 {
  letter-spacing: 0;
}
.steps {
  display: flex;
  gap: 10px;
  align-items: stretch;
  margin: 0;
  padding: 0;
  list-style: none;
}
.step {
  flex: 1 1 0;
  display: flex;
  min-width: 0;
  margin: 0;
}
.step a {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 20px;
  border-radius: 12px;
  border: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg);
  text-decoration: none;
  min-width: 0;
}
.step a:hover {
  border-color: var(--vp-c-text-3);
}
.n {
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-2);
}
.t {
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.d {
  font-size: 13px;
  line-height: 20px;
  color: var(--vp-c-text-2);
}
.chev {
  display: inline-flex;
  align-items: center;
  margin: 0;
  color: var(--vp-c-text-3);
}
.after {
  margin: 0;
  font-size: 15px;
  color: var(--vp-c-text-2);
}
.after a {
  color: var(--vp-c-brand-1);
  font-weight: 600;
  text-decoration: none;
}
@media (max-width: 959px) {
  .steps {
    flex-direction: column;
  }
  .chev {
    display: none;
  }
}
@media (max-width: 639px) {
  .path {
    padding: 56px 0 64px;
  }
  h2 {
    font-size: 26px;
    line-height: 34px;
  }
}
</style>
