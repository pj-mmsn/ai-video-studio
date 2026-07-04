# 🎬 AI Video Studio — 多模型协作视频制作流水线

> **一句话**：推理模型写剧本 → 图像模型画分镜 → 视频模型制成片 → 合成导出 MP4。每个模型做自己最擅长的事。

[![Version](https://img.shields.io/badge/version-2.0-blue)](https://github.com/pj-mmsn/ai-video-studio)
[![Python](https://img.shields.io/badge/python-3.10+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

---

## 🧠 核心理念

传统视频制作需要一个人兼具创意、美术、拍摄能力。AI 视频工作室把这个"全能人"拆成**四个专业 AI Agent + 三个审查员**：

```
你的创意（一句话）
       │
       ▼
┌──────────────────────────────────────────────────┐
│  Stage 1: 🎬 Director（导演 + Few-shot Prompt）   │
│  模型: GPT-4o / DeepSeek-R1（推理模型）           │
│  输出: 结构化剧本（视觉/动效提示词 + 台词 + 镜头） │
│  📖 StoryBible 上下文注入（角色/场景一致性）       │
└────────────────┬─────────────────────────────────┘
                 │ Script  ──→  🔍 Reviewer（审查评分）
                 ▼
┌──────────────────────────────────────────────────┐
│  Stage 2: 🎨 Storyboard（分镜师）                 │
│  模型: DALL-E 3 / Stable Diffusion（图像模型）    │
│  输出: 5-8张分镜图 + 镜头语言标注                 │
└────────────────┬─────────────────────────────────┘
                 │ Shots   ──→  🔍 Reviewer（审查评分）
                 ▼
┌──────────────────────────────────────────────────┐
│  Stage 3: 🎥 Videographer（摄像师）               │
│  模型: RunwayML / Pika / Sora（视频模型）         │
│  输出: 视频片段（每场景一段）                     │
└────────────────┬─────────────────────────────────┘
                 │ Clips   ──→  🔍 Reviewer（最终审查）
                 ▼
┌──────────────────────────────────────────────────┐
│  Stage 4: 🎬 Composer（合成导出）                 │
│  工具: moviepy / ffmpeg                           │
│  输出: video.mp4 + 硬字幕 + 旁白音频              │
└────────────────┬─────────────────────────────────┘
                 │
                 ▼
         🎉 可播放的 MP4 视频
```

**设计模式**：顺序管道 + 反馈循环（CrewAI 模式），每个阶段产出持久化到 SQLite，支持断点续传。

---

## 📂 项目结构

```
ai-video-studio/
│
├── config.py                         # 三模型独立配置
├── requirements.txt                  # 依赖（核心/可选）
├── .env.example                      # API Key 模板
│
├── src/
│   ├── models/__init__.py            # 📡 模型客户端（LLM/Image/Video + Mock）
│   ├── agents/
│   │   ├── director.py               # Stage 1: 剧本导演（Few-shot + 圣经注入）
│   │   ├── storyboard.py             # Stage 2: 分镜师
│   │   ├── videographer.py           # Stage 3: 摄像师
│   │   └── reviewer.py               # 🔍 审查员（CrewAI 反馈循环）
│   ├── db/
│   │   ├── schema.py                 # 💾 6表数据模型
│   │   └── repository.py             # 💾 CRUD + 断点续传 + 进度查询
│   ├── context/
│   │   └── bible.py                  # 📖 故事圣经（跨场景角色/场景一致性）
│   ├── tools/
│   │   └── composer.py               # 🎬 视频合成 + 旁白 + 字幕
│   ├── pipeline/
│   │   └── pipeline.py               # 🔗 编排器（4 Stage + 3 Review）
│   ├── cli/
│   │   └── app.py                    # 💻 CLI（交互式 + 命令行参数）
│   └── logging_config.py             # 📋 统一日志（控制台 + 文件）
│
├── examples/
│   └── demo.py                        # 🚀 一键体验（Mock模式）
│
├── docs/
│   └── OPTIMIZATION_REPORT.md         # 📊 优化分析报告
│
└── output/                            # 📁 产出目录
    ├── projects/<id>/project.db       #   SQLite 项目数据库
    ├── scripts/                       #   剧本 JSON
    ├── storyboard/                    #   分镜图 PNG
    └── video/                         #   MP4 + 字幕
```

---

## 🚀 快速开始

### 1. 一键体验（无需 API Key）

```bash
cd ai-video-studio
pip install -r requirements.txt
python examples/demo.py
```

### 2. 命令行模式

```bash
# Mock 模式
python -m src.cli.app --idea "猫在太空站冒险" --style anime --mock

# 断点续传
python -m src.cli.app --resume proj_1234567890

# 完整模式（需配置 .env）
python -m src.cli.app --idea "赛博朋克爱情故事" --style cinematic --strictness 8

# 查看帮助
python -m src.cli.app --help
```

### 3. 交互模式

```bash
python -m src.cli.app
```

### 4. 配置真实 API

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

---

## 🎮 Python API

```python
from src.pipeline.pipeline import VideoPipeline

# 完整流水线
pipeline = VideoPipeline(
    director_model="gpt-4o",
    use_mock=True,           # Mock 模式，无 API Key
    enable_reviewer=True,    # 启用审查
    reviewer_strictness=6,   # 审查严格度
    project_id="my_film",    # 项目 ID（支持断点续传）
)

production = pipeline.produce("一只猫在太空站冒险", style="anime")
print(production.progress_report())
# 剧本✅ → 分镜✅ → 视频✅ → 合成✅ | 审查3次

# 断点续传——同一个 project_id 再次调用
pipeline2 = VideoPipeline(project_id="my_film")
pipeline2.produce("...")  # 自动跳过已完成阶段

pipeline.close()
```

---

## 🔌 支持的模型

### Stage 1: 剧本导演

| 模型 | 特点 |
|------|------|
| GPT-4o | 创意最佳，指令遵循好 |
| DeepSeek-R1 | 推理强，性价比高 |
| DeepSeek-V3 | 中文优秀 |
| Claude 3.5 Sonnet | 长文本连贯 |

### Stage 2: 分镜师

| 模型 | 特点 |
|------|------|
| DALL-E 3 | 自然语言理解最强 |
| Stable Diffusion XL | 可控性最好（需 Replicate/Fal.ai） |

### Stage 3+4: 摄像+合成

| 工具 | 用途 |
|------|------|
| RunwayML Gen-3 | 图生视频 |
| moviepy | 图片序列 → MP4 |
| edge-tts | 对话 → 语音（免费） |

---

## 🎯 核心特性

| 特性 | 说明 |
|------|------|
| 🔄 断点续传 | SQLite 持久化，崩溃后自动恢复 |
| 📖 StoryBible | LLM 自动提取角色/场景，跨场景一致 |
| 🔍 审查反馈 | 每阶段 Review，不合格自动重试 |
| 🎬 视频合成 | 图片序列 → MP4 + 字幕 + 旁白 |
| 🧪 Mock 模式 | 无 API Key 完整跑通全流程 |
| 📋 命令行 | `--idea` `--style` `--mock` `--resume` |
| 📊 分析报告 | `docs/OPTIMIZATION_REPORT.md` 含优化前后对比 |

---

## 📚 相关知识库

| 文档 | 内容 |
|------|------|
| `Java手册/06-AI与Agent/10-Multi-Agent` | 四种协作模式 |
| `Java手册/06-AI与Agent/06-Prompt工程` | Few-shot 设计 |
| `经验笔记/AI-Agent/多模型协作-视频工作室.md` | 本项目构建经验 |
| `经验笔记/AI-Agent/项目实战-从零构建Agent.md` | 8条常犯错误 |
| 技能: `project-builder` | 从零构建项目的标准流程 |

---

## 📋 同系列项目

| 项目 | 模式 | Agent 数 |
|------|------|:--:|
| [ai-agent-starter](https://github.com/pj-mmsn/ai-agent-starter) | 单 Agent + 工具 | 1 |
| [ai-agent-java](https://github.com/pj-mmsn/ai-agent-java) | 单 Agent (Java) | 1 |
| **ai-video-studio** ⭐ | **多 Agent 管道** | **4** |
