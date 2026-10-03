<script setup lang="ts">
import { ref } from "vue";

// flows: { tab, intro?, steps: [{ who, text, html? }] }
const props = defineProps<{
  flows: { tab: string; intro?: string; steps: { who: string; text: string }[] }[];
}>();
const active = ref(0);
</script>

<template>
  <div class="flows">
    <div class="seg" role="tablist">
      <button
        v-for="(f, i) in props.flows"
        :key="f.tab"
        role="tab"
        :aria-selected="active === i"
        :class="{ on: active === i }"
        @click="active = i"
      >
        {{ f.tab }}
      </button>
    </div>
    <template v-for="(f, i) in props.flows" :key="f.tab">
      <div v-show="active === i" class="panel">
        <p v-if="f.intro" class="intro">{{ f.intro }}</p>
        <ol class="rows">
          <li v-for="(s, n) in f.steps" :key="n">
            <span class="num">{{ n + 1 }}</span>
            <span class="who">{{ s.who }}</span>
            <span class="what" v-html="s.text" />
          </li>
        </ol>
      </div>
    </template>
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
.intro {
  margin: 12px 0 0;
  font-size: 14px;
  color: var(--vp-c-text-2);
}
.rows {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  overflow: hidden;
}
.rows li {
  display: grid;
  grid-template-columns: 28px 150px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
  padding: 12px 16px;
  font-size: 14px;
  line-height: 22px;
  border-top: 1px solid var(--vp-c-divider);
}
.rows li:first-child {
  border-top: 0;
}
.num {
  color: var(--vp-c-text-3);
}
.who {
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.what {
  color: var(--vp-c-text-2);
}
.what :deep(code) {
  font-size: 13px;
}
@media (max-width: 640px) {
  .rows li {
    grid-template-columns: 24px minmax(0, 1fr);
  }
  .what {
    grid-column: 2;
  }
}
</style>
