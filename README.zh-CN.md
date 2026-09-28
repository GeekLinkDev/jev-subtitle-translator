# GeekLink AI 字幕翻译器（含 Jev 质检）

[English](README.md) · **简体中文** · [日本語](README.ja.md) · [한국어](README.ko.md)

一个面向大模型工作流的开源 SRT 字幕翻译与质检工具。用它翻译 SRT 文件、完整保留每一条字幕，并由 Jev 自动检查译文质量。

**关键词：** SRT 翻译 · 字幕质检 · 字幕大模型翻译 · OpenRouter · Jev

![AI 字幕翻译与 Jev 标记需人工复查字幕行的演示](docs/assets/translation-jev-qc.gif)

可使用 GPT、Claude、Gemini、DeepSeek、Grok 或其他兼容的 OpenRouter 模型翻译 SRT 字幕。原字幕的顺序和时间轴保持不变，漏译和可疑的语义偏差都会被明确标出，方便复查。

## 为什么选择这个字幕翻译器？

- **用你偏好的大模型翻译 SRT 字幕。** 根据语言对、质量要求和预算自由选择模型。
- **完整保留每一条字幕。** 原字幕编号、顺序和时间轴都不会改变。
- **杜绝静默漏行。** 缺失或为空的译文会按字幕 ID 重试，仍未解决的会被明确标记。
- **Jev 自动复查译文。** Jev 检查每一对已完成的原文–译文，标出值得人工复查的字幕行。
- **发布前先复查。** 对照原文、译文和复查状态，再下载翻译后的 SRT 与质检报告。
- **本地网页界面或命令行皆可。** 既可以交互式使用，也可以集成进自动化字幕流程。

> **需要从视频而不是 SRT 文件开始？**
>
> 这个开源项目专注于翻译和复查已有的 SRT 字幕。[**试用 GeekLink 字幕翻译器 →**](https://geeklink.dev/subtitle-translator/) 获得完整流程：视频/音频转录、字幕翻译、硬字幕提取、结果编辑和成品视频导出。
>
> *无需配置 Python，也无需管理模型 API。*

## 快速开始

需要 **Python 3.10+** 和一个 **OpenRouter API key**。在 macOS 或 Linux 上：

```bash
git clone https://github.com/GeekLinkDev/jev-subtitle-translator.git
cd jev-subtitle-translator
bash run_web.sh
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，然后：

1. 选择 **Translate + QC**（翻译 + 质检）或 **QC existing translation**（质检已有译文）。
2. 上传原文 SRT。独立质检时还需上传译文 SRT。
3. 填入 OpenRouter API key，选择源语言和目标语言。
4. 点击 **Translate + QC** 或 **Run QC**。独立质检不会调用翻译模型。
5. 复查被高亮的字幕行，并下载 JSON 质检报告。翻译模式还会提供翻译后的 SRT。

视频文件为可选项，添加后可在本地预览字幕效果。

## 如何防止字幕漏行

```text
解析 SRT 并保留每一条字幕
        ↓
按带 ID 的批次翻译
        ↓
校验返回的 ID 与非空译文
        ↓
只重试缺失或为空的 ID
        ↓
运行确定性检查和 Jev 复查
        ↓
基于原字幕列表重建 SRT
```

SRT 在本地解析，原字幕编号、顺序和时间轴都保存在大模型请求之外。每条文本字幕都会分配一个稳定 ID，并通过 JSON Schema 结构化输出进行翻译。

每次响应后，翻译器只接受预期内、唯一且非空的 ID 译文。如果一个 40 条字幕的批次只返回了 35 条有效结果，下一次请求只包含剩余未解决的 5 条。最终 SRT 基于原字幕列表重建，因此某一条翻译失败不会导致后续字幕错位或丢失。

如果某一行最终仍无法翻译，它在输出中的位置会保留为空字幕，质检报告会将其标记为待修复，而不是把失败藏起来。

## 使用 Jev 自动进行翻译质检

本地确定性检查会先在不调用 AI 模型的情况下发现空译文和结构问题。随后，Jev 复查剩余的每一对非空原文–译文，只回答一个问题：**这条译文是否需要人工复查？**

Jev 会标记以下类型的疑似缺陷：

- 漏义、无依据的新增内容，或否定意思被翻转。
- 人名、数字、日期或单位被改动或遗漏。
- 截断、重复或明显错误的内容。

质检按最多 40 条的有序批次进行。判断某一条字幕前，复查模型可以根据句子或说话轮次的需要，查看该批次内任意多条前后字幕。语义合理地跨越字幕边界时不会被标记；如果一个跨多条字幕的句子整体完整，该范围内的每一条都应通过。单词在 token 中间被明显截断时，即使上下文仍能理解，也仍然属于值得复查的缺陷。规则遵循精确率优先：不确定或仅属风格差异的情况应通过，让报告只聚焦于真正值得人工关注的字幕行。

Jev 的标记只是建议你检查这条字幕，并不能证明它一定有错。Jev 不会改写译文，也可能漏掉错误。[复查规则](src/jev_subtitle_translator/qc.py)和 [OpenRouter 请求](src/jev_subtitle_translator/openrouter.py)都可以在源码中查看。

## 支持的输入、模型与输出

- **字幕格式：** 输入 SRT，输出翻译后的 SRT。
- **翻译模型：** 支持严格 JSON Schema 输出的 OpenRouter 模型，包括可用的 GPT、Claude、Gemini、DeepSeek 和 Grok 模型。
- **语言：** 所选翻译模型支持的任意源语言与目标语言组合。
- **质检模型：** 默认使用 OpenRouter 的 `~typesafe/jev-latest` 别名，也可以换成任何其他 OpenRouter 或本地模型。也可以关闭质检，只保留确定性检查。
- **本地模型：** 任何兼容 OpenAI 的服务，例如 Ollama、LM Studio、vLLM 或 llama.cpp。
- **报告：** 翻译后的 SRT，以及包含逐行翻译和复查状态的 JSON 报告。

## 命令行

翻译 SRT 并自动运行 Jev 复查：

```bash
export OPENROUTER_API_KEY="your-api-key"

.venv/bin/jev-subtitle-translator translate input.srt \
  --source-language en --target-language de \
  --model openai/gpt-4o-mini --output translated.srt
```

只复查已有译文、不重新翻译：

```bash
export OPENROUTER_API_KEY="your-api-key"

.venv/bin/jev-subtitle-translator qc \
  --source input.srt --translation translated.srt \
  --source-language en --target-language de --output qc-report.json
```

翻译命令会写出 `translated.srt` 和 `translated.srt.qc.json`。用 `--prompt` 添加额外的翻译要求，用 `--batch-size` 和 `--workers` 调整请求，或运行任一命令的 `--help` 查看全部选项。

## 本地模型与兼容 OpenAI 的模型

翻译和质检都可以分别指向任何提供 OpenAI 兼容 `/v1/chat/completions` 接口的服务。在网页界面中选择 **Local / OpenAI-compatible** 并填入 base URL，例如 Ollama 用 `http://localhost:11434/v1`、LM Studio 用 `http://localhost:1234/v1`、vLLM 用 `http://localhost:8000/v1`。

```bash
# 本地翻译，在 OpenRouter 上用 Jev 复查
export OPENROUTER_API_KEY="your-api-key"
.venv/bin/jev-subtitle-translator translate input.srt \
  --source-language en --target-language de \
  --model qwen2.5:14b --base-url http://localhost:11434/v1 --output translated.srt

# 完全本地：用本地模型翻译和复查，无需 OpenRouter key
.venv/bin/jev-subtitle-translator translate input.srt \
  --source-language en --target-language de \
  --model qwen2.5:14b --base-url http://localhost:11434/v1 \
  --qc-model qwen2.5:14b --qc-base-url http://localhost:11434/v1 --output translated.srt
```

只有访问 openrouter.ai 上的接口时才需要 `OPENROUTER_API_KEY`；如果本地服务需要 key，请设置 `LOCAL_API_KEY`。Jev 模型（`typesafe/jev-*` 和 `~typesafe/jev-*`）使用 OpenRouter 的 Decisions 接口，因此必须通过 OpenRouter。其他质检模型会通过 chat 接收同一套复查规则，并逐行返回 `needs_review` 判定。使用 `--qc-model none` 可跳过语义质检。

翻译器会请求 JSON Schema 结构化输出，目前大多数本地服务都支持。如果模型仍把 JSON 包在普通文本或 markdown 中，会自动提取其中的对象。小型本地模型漏掉 ID 的情况可能更多，这些行会像其他失败一样先重试、再标记。

## 常见问题

### 会保留 SRT 时间轴吗？

会。字幕编号、顺序和时间轴都在本地解析和保存，只有对白文本及其稳定 ID 会被发送去翻译。

### 如何防止字幕漏行？

每次模型响应都会与预期的字幕 ID 逐一校验。缺失或为空的结果会单独重试，仍未解决的行会在输出和质检报告中保持可见。

### Jev 会自动修正错误的译文吗？

不会。Jev 只标出可能需要人工复查的字幕，不会替换或改写译文。

### 这个字幕翻译器免费吗？

本项目以 GPL 协议免费开源。你需要自备 OpenRouter API key，翻译和 Jev 请求可能产生 OpenRouter 费用。界面在本地运行，但字幕文本会发送给 OpenRouter 以及你选择的模型提供商。

### 这个项目和 GeekLink 有什么区别？

本项目专注于翻译和复查已有的 SRT 文件。[GeekLink](https://geeklink.dev/subtitle-translator/) 是面向创作者的完整桌面应用，涵盖转录、翻译、硬字幕提取、字幕编辑和视频导出。

## 开发与许可证

使用 `.venv/bin/python -m pip install -e ".[dev]"` 安装测试依赖，并运行 `.venv/bin/python -m pytest -q`。如需贡献修复或可复现的字幕样例，请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

基于 [GPL-3.0-or-later](LICENSE) 许可证发布。Copyright (C) 2026 GeekLinkDev。
