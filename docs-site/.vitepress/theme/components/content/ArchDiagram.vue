<script setup lang="ts">
import { computed } from "vue";
import { useData } from "vitepress";

const { lang } = useData();
const zh = computed(() => lang.value.startsWith("zh"));

const T = computed(() =>
  zh.value
    ? {
        clients: "本机上的客户端",
        shim: ["coffer-mcp-shim", "每个智能体会话一个"],
        cli: ["coffer", "命令行"],
        web: ["Web 界面", "由守护进程提供"],
        desk: ["桌面应用", "原生窗口"],
        link1: "/mcp · /api/v1",
        on: "位于 127.0.0.1 · 唯一的写入者",
        gw: ["MCP 网关 /mcp", "合并上游服务器，按生效范围过滤"],
        proxy: ["模型代理", "加上提供商密钥后转发上游"],
        api: ["HTTP API /api/v1", "管理平面"],
        rf: ["资源框架", "每种类型共用的身份、生命周期、审计和生效范围"],
        wk: ["后台 worker", "同步、记忆、渠道"],
        link2: "读写 · 仅出站",
        vault: "~/.coffer · 保险库，一个 git 仓库",
        vaultFiles: ["vault/", "资源、技能、知识、记忆、密文"],
        db: ["runs.db", "历史记录"],
        out: "仅出站",
        up: ["MCP 服务器", "上游"],
        mp: ["模型提供商", "上游"],
        im: ["Telegram · SeaTalk", "渠道"],
        git: ["Git 远端", "可选"],
        note: "带轮廓的方框是一个进程，它是保险库的唯一写入者；其他方框都通过回环地址作为它的客户端。",
      }
    : {
        clients: "Clients on this machine",
        shim: ["coffer-mcp-shim", "one per agent session"],
        cli: ["coffer", "the CLI"],
        web: ["Web UI", "served by the daemon"],
        desk: ["Desktop app", "native window"],
        link1: "/mcp · /api/v1",
        on: "on 127.0.0.1 · the only writer",
        gw: ["MCP gateway /mcp", "merges upstream servers, filters by reach"],
        proxy: ["Model proxy", "adds the provider key upstream"],
        api: ["HTTP API /api/v1", "the management plane"],
        rf: ["Resource framework", "identity, lifecycle, audit and reach for every kind"],
        wk: ["Workers", "sync, memory, channels"],
        link2: "reads, writes · outbound",
        vault: "~/.coffer · the vault, a git repository",
        vaultFiles: ["vault/", "resources, skills, knowledge, memory, ciphertext"],
        db: ["runs.db", "history"],
        out: "Outbound only",
        up: ["MCP servers", "upstream"],
        mp: ["Model providers", "upstream"],
        im: ["Telegram · SeaTalk", "channels"],
        git: ["Git remote", "optional"],
        note: "The outlined box is one process. It is the only writer of the vault; every other box is a client of it over loopback.",
      },
);
</script>

<template>
  <figure class="arch">
    <div class="group">
      <div class="group-title">{{ T.clients }}</div>
      <div class="row cols-4">
        <div v-for="c in [T.shim, T.cli, T.web, T.desk]" :key="c[0]" class="node">
          <div class="n-title" :class="{ mono: c === T.shim || c === T.cli }">{{ c[0] }}</div>
          <div class="n-sub">{{ c[1] }}</div>
        </div>
      </div>
    </div>

    <div class="link"><span class="arrow" /><span class="link-label">{{ T.link1 }}</span></div>

    <div class="group daemon">
      <div class="group-title">
        <span class="mono strong">coffer-daemon</span> <span class="muted">{{ T.on }}</span>
      </div>
      <div class="row cols-3">
        <div v-for="c in [T.gw, T.proxy, T.api]" :key="c[0]" class="node">
          <div class="n-title">{{ c[0] }}</div>
          <div class="n-sub">{{ c[1] }}</div>
        </div>
      </div>
      <div class="row cols-2-1">
        <div v-for="c in [T.rf, T.wk]" :key="c[0]" class="node">
          <div class="n-title">{{ c[0] }}</div>
          <div class="n-sub">{{ c[1] }}</div>
        </div>
      </div>
    </div>

    <div class="link"><span class="arrow" /><span class="link-label">{{ T.link2 }}</span></div>

    <div class="bottom">
      <div class="group">
        <div class="group-title">{{ T.vault }}</div>
        <div class="row cols-2">
          <div v-for="c in [T.db, T.vaultFiles]" :key="c[0]" class="node">
            <div class="n-title mono">{{ c[0] }}</div>
            <div class="n-sub">{{ c[1] }}</div>
          </div>
        </div>
      </div>
      <div class="group">
        <div class="group-title">{{ T.out }}</div>
        <div class="row cols-2">
          <div v-for="c in [T.up, T.mp, T.im, T.git]" :key="c[0]" class="node">
            <div class="n-title">{{ c[0] }}</div>
            <div class="n-sub">{{ c[1] }}</div>
          </div>
        </div>
      </div>
    </div>
    <figcaption>{{ T.note }}</figcaption>
  </figure>
</template>

<style scoped>
.arch {
  margin: 20px 0 0;
}
.group {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 12px;
}
.group.daemon {
  background: var(--vp-c-bg);
  border: 1.5px solid var(--vp-c-text-1);
}
.group-title {
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
  color: var(--vp-c-text-2);
  margin-bottom: 8px;
}
.group.daemon .group-title {
  color: var(--vp-c-text-1);
}
.muted {
  color: var(--vp-c-text-2);
  font-weight: 400;
}
.strong {
  font-weight: 700;
  color: var(--vp-c-text-1);
}
.row {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}
.row:first-of-type {
  margin-top: 0;
}
.cols-4 {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.cols-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.cols-2-1 {
  grid-template-columns: 2fr 1fr;
}
.node {
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  padding: 10px 12px;
  min-width: 0;
}
.n-title {
  font-size: 14px;
  line-height: 22px;
  font-weight: 600;
  color: var(--vp-c-text-1);
  overflow-wrap: anywhere;
}
.n-sub {
  font-size: 13px;
  line-height: 20px;
  color: var(--vp-c-text-2);
}
.mono {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
}
.link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 0 0 22%;
  height: 36px;
}
.arrow {
  width: 1px;
  height: 100%;
  background: var(--vp-c-text-3);
  position: relative;
}
.arrow::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: -3px;
  border: 3.5px solid transparent;
  border-top: 6px solid var(--vp-c-text-3);
  border-bottom: 0;
}
.link-label {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-text-2);
}
.bottom {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
figcaption {
  margin-top: 12px;
  font-size: 13px;
  line-height: 20px;
  color: var(--vp-c-text-2);
}
@media (max-width: 640px) {
  .cols-4,
  .cols-3,
  .cols-2-1,
  .bottom {
    grid-template-columns: 1fr 1fr;
  }
  .cols-2-1,
  .bottom {
    grid-template-columns: 1fr;
  }
}
</style>
