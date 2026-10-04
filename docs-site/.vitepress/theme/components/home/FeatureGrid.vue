<script setup lang="ts">
import { withBase } from "vitepress";
import { computed } from "vue";
import { STR, type Lang } from "./homeStrings";

const props = defineProps<{ lang: Lang }>();
const s = computed(() => STR[props.lang]);
const href = (p: string) => withBase((props.lang === "zh" ? "/zh" : "") + p);
</script>

<template>
  <section class="features" aria-label="Features">
    <div class="in">
      <div v-for="(g, gi) in s.groups" :key="g.label" class="group">
        <div class="ghead">
          <span class="glabel">{{ g.label }}</span>
          <a v-if="gi === 0" class="link" :href="href('/guides/')">
            {{ s.allGuides }}<HomeIcon name="arrow" :size="14" />
          </a>
        </div>
        <div class="grid">
          <div v-for="it in g.items" :key="it[1] as string" class="card">
            <span class="top">
              <HomeIcon :name="it[0] as string" :size="20" class="ico" />
              <span v-if="it[5]" class="tag">{{ s.exp }}</span>
            </span>
            <h3>{{ it[1] }}</h3>
            <p>{{ it[2] }}</p>
            <a class="link" :href="href(it[4] as string)">
              {{ it[3] }}<HomeIcon name="arrow" :size="14" />
            </a>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.in {
  width: min(1184px, calc(100% - 48px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 40px;
}
.features {
  padding: 0 0 96px;
}
.group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ghead {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.glabel {
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
  color: var(--vp-c-text-2);
}
.grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
}
.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 22px 24px;
  border-radius: 12px;
  border: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg);
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ico {
  color: var(--vp-c-text-2);
}
.tag {
  display: inline-flex;
  align-items: center;
  height: 16px;
  padding: 0 4px;
  box-sizing: border-box;
  border: 1px solid var(--vp-c-border);
  border-radius: 4px;
  font-size: 11px;
  line-height: 1;
  color: var(--vp-c-text-2);
  white-space: nowrap;
}
h3 {
  margin: 6px 0 0;
  padding: 0;
  border: 0;
  font-size: 17px;
  line-height: 26px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--vp-c-text-1);
}
p {
  margin: 0;
  flex-grow: 1;
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
}
.link {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 6px;
  margin-top: 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}
.ghead .link {
  margin-top: 0;
}
@media (max-width: 1099px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 639px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .features {
    padding-bottom: 64px;
  }
}
</style>
