# ADR-039：冻结 App 的语音转写用随包 whisper.cpp sidecar

> English: [ADR-039-frozen-stt-whispercpp.md](ADR-039-frozen-stt-whispercpp.md)

**状态**：已接受
**日期**：2026-07-04
**决策者**：Yuxing Wu
**相关**：spec `009-channels`（FR-022）；构建于 [ADR-038](ADR-038-channel-media.zh.md)（channel media，按 agent 的转写接缝）之上

## 背景

spec 009 FR-022 通过 `Transcriber` 接缝，把入站语音消息为纯文本 agent（Claude Code、
Codex）转写成文字。源码运行的引擎是 `mlx-whisper`（可选 `[voice]` extra），惰性 import
以保持依赖可选。

这句惰性 import 击穿了冻结构建。PyInstaller 会扫描函数体,所以 `transcribe.py` 里的
`import mlx_whisper` 会把 `torch` + `mlx` + `numba` + `llvmlite` + `scipy` 拖进**每一个**
`coffer-*` 二进制(每个 `collect_submodules("coffer")` 都拉进整个包)。二进制从 ~94 MB
膨胀到 ~260 MB,而且 `torch` 在 PyInstaller 下很脆。现有的绕法是在打包前卸载
`mlx-whisper`——于是在冻结的桌面 App 里惰性 import 失败,语音悄悄降级为"把音频文件交给
agent"而非转写。**已发布的 App 无法转写语音。**

我们要让冻结 App **本地**转写入站语音(Coffer 是 local-first)、**torch-free**、在 Apple
Silicon 上有 **Metal 加速**,同时保持二进制精简。

## 决策

**随包一个 torch-free 的 `whisper.cpp` sidecar,并让冻结构建从构造上就精简;
`mlx-whisper` 保留为源码运行的 fallback。**

1. **从构造上精简。** 每个做 `collect_submodules("coffer")` 的 `coffer-*.spec` 都加上重
   ML `excludes`(`torch`、`mlx`、`mlx_whisper`、`numba`、`llvmlite`、`scipy`、`sympy`、
   `networkx`、`mpmath`)。于是 `[voice]` extra 可以留在 build venv 里而二进制仍保持 ~95 MB
   且 torch-free。

2. **STT 作为 sidecar 二进制**,照 `coffer-callback`(ADR/PR #240)的模式:`whisper.cpp` 的
   `whisper-cli`(Apple Silicon Metal,无 Python/torch)从**固定 tag**(`v1.9.1`)在
   `build_binaries.sh` 里编出,经 Tauri `externalBin` 打包,由 `shim.rs` 与其它 sidecar 一起
   部署到 `~/.coffer/bin`。daemon 冻结时把它解析为自身可执行文件的 sibling,源码运行时走
   `PATH`。

3. **`WhisperCppTranscriber` 实现接缝。** 它用 `soundfile`(libsndfile 能读 OGG/Opus——
   Telegram 语音格式——以及 wav/flac/mp3)**在进程内**解码,用 `soxr` 重采样到 16 kHz 单
   声道,写临时 WAV,再 shell out `whisper-cli`。`soundfile` + `soxr` 就是小巧、torch-free 的
   `[voice]` extra,保留在冻结构建里(不排除)。任一缺失(二进制、模型、解码器)返回 `""`,
   让 adapter 回退为交出文件——接缝永不抛错。

4. **模型首次使用时下载。** `ggml-base-q5_1` 多语言模型(~57 MB)首次使用时下载一次到
   `~/.coffer/models/`(whisper.cpp 的 `models/` 惯例),不随包,以保持 DMG 精简。首条语音
   离线时降级为文件交付,直到模型缓存好。

5. **择优选择。** `default_transcriber()` 挑引擎:`whisper.cpp`(冻结,或源码且 `PATH` 上有
   `whisper-cli`)→ `mlx-whisper`(源码运行 fallback)→ `None`。接缝不变,所以 FR-022 验收
   测试仍驱动一个 fake transcriber。

## 备选方案

- **把 `mlx-whisper` 单独冻结成 sidecar** —— daemon 保持精简但仍发布一个 ~260 MB 的 `torch`
  二进制及其 PyInstaller 脆性;只是挪走了重量。否决——没解决问题本身。
- **`faster-whisper`(CTranslate2)冻结 sidecar** —— torch-free 且 PyInstaller 友好,进程内
  解码用 PyAV,但在 Apple Silicon 上**只有 CPU**(无 Metal/ANE),sidecar ~150 MB。否决——
  放弃了 `whisper.cpp` 免费拿到的硬件加速。
- **`sherpa-onnx`(ONNX Runtime + CoreML EP)** —— 能上 ANE,但需把 Whisper 转 ONNX、对此
  场景成熟度较低、且仍需另配解码器。搁置。
- **随包 `ffmpeg` 做解码** —— 通用(m4a/amr/…),但多一个重二进制。`soundfile`/libsndfile
  已能解 OGG/Opus 语音场景(在 macOS arm64 上实测)以及进程内的 wav/flac/mp3。选了精简的
  进程内路径;冷门格式降级为文件交付。
- **模型随包内置** —— 离线优先但 DMG +57 MB。为精简 DMG 否决;改为首次使用时下载到
  `~/.coffer/models/`。

## 后果

- 冻结的桌面 App **本地、torch-free、Metal 加速地**转写入站语音;即使 build 时装了
  `[voice]`,所有 `coffer-*` 二进制仍保持 ~95 MB。
- `make bundle-binaries` 现在需要 **`cmake` + 联网 + 一次性 C++ 构建** whisper.cpp(固定、
  缓存在 `build/` 下)。CI `desktop-build` 与本地桌面构建都要有 `cmake`(`brew install cmake`);
  缺失时脚本明确报错。
- `[voice]` extra 现在就是 torch-free 的解码栈(`soundfile` + `soxr`),装进冻结 build venv
  并打进 daemon(体积小)。`mlx-whisper` 移到单独的 `[voice-mlx]` extra(仅源码运行
  fallback),排除在冻结构建外。
- libsndfile 解不了的格式(如 m4a/aac)回退为文件交付——与"转写不可用"同一条优雅路径。
- `~/.coffer/models/` 下会积累一个小模型;留存不成问题。
