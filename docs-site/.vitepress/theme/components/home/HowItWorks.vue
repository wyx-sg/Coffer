<script setup lang="ts">
import { withBase } from "vitepress";
import { computed } from "vue";
import { STR, type Lang } from "./homeStrings";

const props = defineProps<{ lang: Lang }>();
const s = computed(() => STR[props.lang]);
const href = (p: string) => withBase((props.lang === "zh" ? "/zh" : "") + p);
</script>

<template>
  <section class="how" aria-labelledby="how-it-works">
    <div class="in">
      <div class="head">
        <div class="htext">
          <h2 id="how-it-works">{{ s.how }}</h2>
          <p>{{ s.howLead }}</p>
        </div>
        <a class="link" :href="href('/architecture/')">
          {{ s.arch }}<HomeIcon name="arrow" :size="15" />
        </a>
      </div>

      <div class="diagram" role="img" :aria-label="s.diagramLabel">
        <div class="you">
          <span class="ylabel">{{ s.you }}</span>
          <span class="pills"
            ><span v-for="p in s.youItems" :key="p" class="pill">{{ p }}</span></span
          >
          <span class="down" />
        </div>

        <div class="c c-agents">
          <div class="card">
            <span class="ct">{{ s.agents.title }}</span>
            <span class="cs">{{ s.agents.sub }}</span>
            <div v-for="r in s.agents.rows" :key="r[1]" class="row">
              <span v-if="r[0]" class="badge">{{ r[0] }}</span>
              <span v-else class="spacer" />
              <span>{{ r[1] }}</span>
              <span class="meta">{{ r[2] }}</span>
            </div>
          </div>
        </div>
        <div class="c c-a1">
          <div class="arr"><span class="al">{{ s.arrows[0] }}</span><span class="ln" /></div>
        </div>
        <div class="c c-coffer">
          <div class="card strong">
            <span class="ct">{{ s.coffer.title }}</span>
            <span class="cs">{{ s.coffer.sub }}</span>
            <div v-for="r in s.coffer.rows" :key="r[1]" class="row">
              <HomeIcon :name="r[0]" :size="15" class="ri" />
              <span>{{ r[1] }}</span>
              <span class="meta">{{ r[2] }}</span>
            </div>
            <span class="foot">{{ s.coffer.foot }}</span>
          </div>
        </div>
        <div class="c c-a2">
          <div class="arr"><span class="al">{{ s.arrows[1] }}</span><span class="ln" /></div>
        </div>
        <div class="c c-vault">
          <div class="card">
            <span class="ct">{{ s.vault.title }}</span>
            <span class="cs">{{ s.vault.sub }}</span>
            <div v-for="r in s.vault.rows" :key="r[1]" class="row">
              <HomeIcon name="folder" :size="15" class="ri" />
              <span class="mono">{{ r[1] }}</span>
              <span class="meta">{{ r[2] }}</span>
            </div>
            <span class="foot">{{ s.vault.foot }}</span>
          </div>
        </div>
        <div class="c c-a3">
          <div class="arr"><span class="al">{{ s.arrows[2] }}</span><span class="ln" /></div>
        </div>
        <div class="c c-remote">
          <div class="remote">
            <span class="rt"><HomeIcon name="branch" :size="15" class="ri" />{{ s.remote.title }}</span>
            <span class="meta2">{{ s.remote.sub }}</span>
            <span class="tag">{{ s.exp }}</span>
            <span class="meta2">{{ s.remote.note }}</span>
          </div>
        </div>
      </div>

      <div class="take">
        <p v-for="t in s.takeaways" :key="t[0]">
          <strong>{{ t[0] }}</strong> {{ t[1] }}<template v-if="t[2]">
            <code>{{ t[2] }}</code> {{ t[3] }}</template
          >
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.how {
  padding: 80px 0;
  background: var(--vp-c-bg-alt);
  border-top: 1px solid var(--vp-c-border);
  border-bottom: 1px solid var(--vp-c-border);
}
.in {
  width: min(1184px, calc(100% - 48px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 48px;
}
.htext {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 720px;
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
.htext p {
  margin: 0;
  font-size: 18px;
  line-height: 30px;
  color: var(--vp-c-text-2);
}
.link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}

/* diagram */
.diagram {
  display: grid;
  grid-template-columns: minmax(0, 230fr) 74px minmax(0, 300fr) 74px minmax(0, 250fr) 64px minmax(0, 192fr);
  align-items: center;
  row-gap: 8px;
}
.you {
  grid-column: 2 / 5;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.ylabel {
  font-size: 13px;
  color: var(--vp-c-text-2);
}
.pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
}
.pill {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg);
  font-size: 13px;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}
.down {
  position: relative;
  width: 1.5px;
  height: 22px;
  background: var(--vp-c-text-3);
  margin-bottom: 6px;
}
.down::after {
  content: "";
  position: absolute;
  left: -4.25px;
  top: 100%;
  border: 5px solid transparent;
  border-top: 8px solid var(--vp-c-text-3);
  border-bottom: 0;
}
.c {
  grid-row: 2;
  min-width: 0;
}
.c-agents { grid-column: 1; }
.c-a1 { grid-column: 2; }
.c-coffer { grid-column: 3; }
.c-a2 { grid-column: 4; }
.c-vault { grid-column: 5; }
.c-a3 { grid-column: 6; }
.c-remote { grid-column: 7; }

.card {
  display: flex;
  flex-direction: column;
  padding: 18px 18px 16px;
  box-sizing: border-box;
  border-radius: 12px;
  border: 1px solid var(--vp-c-border);
  background: var(--vp-c-bg);
}
.card.strong {
  box-shadow: 0 0 0 1px var(--vp-c-border);
}
.ct {
  font-size: 17px;
  line-height: 26px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.cs {
  margin-bottom: 12px;
  font-size: 13px;
  line-height: 20px;
  color: var(--vp-c-text-2);
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 38px;
  border-top: 1px solid var(--vp-c-divider);
  font-size: 14px;
  color: var(--vp-c-text-1);
}
.row .mono {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
}
.ri {
  color: var(--vp-c-text-3);
}
.meta {
  margin-left: auto;
  font-size: 13px;
  color: var(--vp-c-text-2);
  text-align: right;
}
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-border);
  font-size: 9px;
  font-weight: 700;
  color: var(--vp-c-text-2);
  flex-shrink: 0;
}
.spacer {
  width: 18px;
  flex-shrink: 0;
}
.foot {
  margin-top: 12px;
  font-size: 13px;
  line-height: 20px;
  color: var(--vp-c-text-2);
}
.arr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
}
.al {
  font-size: 12px;
  line-height: 16px;
  font-weight: 500;
  color: var(--vp-c-text-2);
  text-align: center;
  white-space: nowrap;
}
.ln {
  position: relative;
  display: block;
  width: 100%;
  height: 10px;
  background: linear-gradient(var(--vp-c-text-3), var(--vp-c-text-3)) center / 100% 1.5px no-repeat;
}
.ln::before,
.ln::after {
  content: "";
  position: absolute;
  top: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
}
.ln::before {
  left: 0;
  border-right: 8px solid var(--vp-c-text-3);
}
.ln::after {
  right: 0;
  border-left: 8px solid var(--vp-c-text-3);
}
.remote {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  padding: 16px;
  box-sizing: border-box;
  border-radius: 12px;
  border: 1px dashed var(--vp-c-text-3);
}
.rt {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.meta2 {
  font-size: 13px;
  line-height: 20px;
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
.take {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  column-gap: 32px;
  font-size: 14px;
  line-height: 22px;
  color: var(--vp-c-text-2);
}
.take p {
  margin: 0;
}
.take strong {
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.take code {
  font-size: 13px;
  padding: 0 4px;
  border-radius: 4px;
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-1);
}

@media (max-width: 1099px) {
  .diagram {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 0;
    justify-items: stretch;
  }
  .you,
  .c {
    grid-column: 1 !important;
    grid-row: auto;
  }
  .you {
    margin-bottom: 4px;
  }
  .arr {
    flex-direction: row;
    justify-content: center;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
  }
  .ln {
    width: 10px;
    height: 36px;
    background: linear-gradient(var(--vp-c-text-3), var(--vp-c-text-3)) center / 1.5px 100% no-repeat;
  }
  .ln::before,
  .ln::after {
    top: auto;
    left: 0;
    right: auto;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 0;
    border-bottom: 0;
  }
  .ln::before {
    top: 0;
    border-bottom: 8px solid var(--vp-c-text-3);
  }
  .ln::after {
    bottom: 0;
    border-top: 8px solid var(--vp-c-text-3);
  }
  .take {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 12px;
  }
}
@media (max-width: 639px) {
  .how {
    padding: 56px 0;
  }
  .head {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }
  h2 {
    font-size: 26px;
    line-height: 34px;
  }
  .htext p {
    font-size: 16px;
    line-height: 26px;
  }
}
</style>
