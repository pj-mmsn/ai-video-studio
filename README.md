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
│  Stage 1: 🎬 Director（剧本导演）                 │
│  擅长: 创意推理、结构化输出                        │
│  推荐: GPT-4o / DeepSeek-R1                      │
│  输出: 场景列表（视觉/动效提示词 + 台词 + 镜头）   │
│  📖 StoryBible 上下文注入（角色/场景一致性）       │
└────────────────┬─────────────────────────────────┘
                 │ Script  ──→  🔍 Review
                 ▼
┌──────────────────────────────────────────────────┐
│  Stage 2: 🎨 Storyboard（分镜师）                 │
│  擅长: 文字→图像跨模态生成                         │
│  推荐: DALL-E 3 / Stable Diffusion               │
│  输出: 5-8张分镜图 + 镜头语言标注                 │
└────────────────┬─────────────────────────────────┘
                 │ Shots   ──→  🔍 Review
                 ▼
┌──────────────────────────────────────────────────┐
│  Stage 3: 🎥 Videographer（摄像师）               │
│  擅长: 图像→视频动态生成                           │
│  推荐: RunwayML / Pika / Sora                    │
│  输出: 视频片段（每场景一段）                     │
└────────────────┬─────────────────────────────────┘
                 │ Clips   ──→  🔍 Review
                 ▼
┌──────────────────────────────────────────────────┐
│  Stage 4: 🎬 Composer（合成导出）                 │
│  本地工具: 图片序列 → MP4 + 字幕 + 旁白            │
│  输出: 可播放的视频文件                           │
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

```bash
# 1. 安装依赖
cd ai-video-studio
pip install -r requirements.txt

# 2. 一键体验（Mock 模式，零配置，零成本）
python examples/demo.py

# 3. 接真实 API（可选——只填一行就能让 Stage1 用上真 LLM）
cp .env.example .env
# 编辑 .env → 填 LLM_API_KEY

# 4. 命令行运行
python -m src.cli.app --idea "猫在太空站冒险" --style anime
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

## 🔌 模型选用

核心理念：**不同任务用不同擅长的模型**——推理模型写剧本、图像模型画分镜、视频模型制成片。

### 最小配置（1 个 Key 即可跑通 Stage 1+2+3+4）

```bash
# .env —— 一个 OpenAI 兼容 Key 覆盖 Stage1(剧本) + Stage2(分镜图)
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.deepseek.com/v1    # DeepSeek / OpenAI / 智谱 任选
LLM_MODEL=deepseek-chat
```

| 阶段 | 用哪个模型 | 最小配置下 |
|------|-----------|-----------|
| Stage 1 剧本 | GPT-4o / DeepSeek-R1 / DeepSeek-V3 | ✅ 真实 LLM 生成 |
| Stage 2 分镜图 | DALL-E 3 | ⚠️ 共用 LLM Key 或降级 Mock 占位图 |
| Stage 3 视频片段 | RunwayML / Pika | ⚠️ 需单独 Key 或降级 Mock 静态帧 |
| Stage 4 合成导出 | moviepy（本地工具） | ✅ 不需要任何 Key |

### 完整配置（每个阶段专用模型，效果最佳）

```bash
# Stage 1: 剧本——推理模型
DIRECTOR_API_KEY=sk-xxx
DIRECTOR_MODEL=gpt-4o          # 或 deepseek-reasoner（推理更强）

# Stage 2: 分镜图——图像生成模型
IMAGE_API_KEY=sk-xxx
IMAGE_MODEL=dall-e-3           # 或 stable-diffusion-xl（需 Replicate API）

# Stage 3: 视频片段——视频生成模型（可选，目前 API 未完全开放）
VIDEO_API_KEY=your-key
VIDEO_MODEL=runway-gen3        # 或 pika-labs
```

> 建议：先用最小配置跑 Mock 模式体验流程 → 配一个 LLM Key 升级 Stage1 → 有需要再加图像/视频 Key。

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
