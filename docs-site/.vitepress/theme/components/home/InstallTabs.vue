<script setup lang="ts">
import { withBase } from "vitepress";
import { computed, ref } from "vue";
import { PROMPT, RELEASES, SHELL_CMD, STR, type Lang } from "./homeStrings";

const props = defineProps<{ lang: Lang }>();
const s = computed(() => STR[props.lang]);
const href = (p: string) => withBase((props.lang === "zh" ? "/zh" : "") + p);

type Tab = "desktop" | "agent" | "shell";
const tab = ref<Tab>("desktop");
const copied = ref<"" | "agent" | "shell">("");
let timer: ReturnType<typeof setTimeout> | undefined;

const tabs = computed<{ id: Tab; label: string }[]>(() => [
  { id: "desktop", label: s.value.tabDesktop },
  { id: "agent", label: s.value.tabAgent },
  { id: "shell", label: s.value.tabShell },
]);

async function copy(kind: "agent" | "shell") {
  const text = kind === "agent" ? PROMPT : SHELL_CMD;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
    } catch {
      /* ignore */
    }
    ta.remove();
  }
  copied.value = kind;
  clearTimeout(timer);
  timer = setTimeout(() => (copied.value = ""), 1800);
}
</script>

<template>
  <div class="install">
    <div class="bar">
      <span class="label">{{ s.install }}</span>
      <div class="seg" role="tablist">
        <button
          v-for="t in tabs"
          :key="t.id"
          type="button"
          role="tab"
          :aria-selected="tab === t.id"
          :class="{ on: tab === t.id }"
          @click="tab = t.id"
        >
          {{ t.label }}
        </button>
      </div>
    </div>
    <div class="box" role="tabpanel">
      <template v-if="tab === 'desktop'">
        <div class="dl-row">
          <a class="dl" :href="RELEASES" target="_blank" rel="noreferrer">
            <HomeIcon name="download" :size="16" />{{ s.download }}
          </a>
          <span class="muted">{{ s.dlMeta }}</span>
        </div>
        <span class="muted">{{ s.dlNote }}</span>
        <a class="more" :href="href('/start/install')">{{ s.other }} →</a>
      </template>
      <template v-else-if="tab === 'agent'">
        <p class="prompt">{{ PROMPT }}</p>
        <div class="foot">
          <span class="muted">{{ s.note }}</span>
          <button type="button" class="copy" @click="copy('agent')">
            <HomeIcon :name="copied === 'agent' ? 'check' : 'copy'" :size="14" />
            {{ copied === "agent" ? s.copied : s.copyPrompt }}
          </button>
        </div>
      </template>
      <template v-else>
        <div class="code">
          <code>{{ SHELL_CMD }}</code>
        </div>
        <div class="foot">
          <span class="muted">{{ s.note }}</span>
          <button type="button" class="copy" @click="copy('shell')">
            <HomeIcon :name="copied === 'shell' ? 'check' : 'copy'" :size="14" />
            {{ copied === "shell" ? s.copied : s.copyCmd }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.install {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.label {
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.seg {
  display: inline-flex;
  padding: 2px;
  border-radius: 8px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
}
.seg button {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  color: var(--vp-c-text-2);
  cursor: pointer;
}
.seg button.on {
  background: var(--vp-c-bg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08), 0 0 0 1px var(--vp-c-border);
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.box {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 16px 16px;
  border-radius: 10px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  min-width: 0;
}
.muted {
  font-size: 13px;
  line-height: 20px;
  color: var(--vp-c-text-2);
}
.dl-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.dl {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 16px;
  box-sizing: border-box;
  border-radius: 8px;
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-border);
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-text-1);
  text-decoration: none;
}
.more {
  align-self: flex-start;
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}
.prompt {
  margin: 0;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 22px;
  color: var(--vp-c-text-1);
  max-height: 132px;
  overflow: auto;
}
.code {
  overflow-x: auto;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-divider);
}
.code code {
  white-space: nowrap;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 22px;
  color: var(--vp-c-text-1);
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.copy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 10px;
  flex-shrink: 0;
  border-radius: 7px;
  border: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg);
  font: inherit;
  font-size: 13px;
  font-weight: 550;
  color: var(--vp-c-text-1);
  cursor: pointer;
}
@media (max-width: 639px) {
  .foot {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
