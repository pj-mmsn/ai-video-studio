# 🎬 AI Video Studio — 多模型协作视频制作流水线

> **一句话**：让推理模型写剧本、图像模型画分镜、视频模型制成片——每个模型做自己最擅长的事。

---

## 🧠 核心理念

传统视频制作需要一个人（或团队）同时具备创意、美术、拍摄能力。AI 视频工作室把这个"全能人"拆成三个专业 AI Agent：

```
你的创意（一句话）
       │
       ▼
┌──────────────────────────────────────────────┐
│  Stage 1: 🎬 Director（导演）                │
│  模型: GPT-4o / DeepSeek-R1（推理模型）       │
│  输入: "一只猫在太空站冒险"                   │
│  输出: 结构化剧本（5-8个场景，视觉/动效提示词） │
└──────────────────┬───────────────────────────┘
                   │ Script
                   ▼
┌──────────────────────────────────────────────┐
│  Stage 2: 🎨 Storyboard（分镜师）            │
│  模型: DALL-E 3 / Stable Diffusion（图像模型）│
│  输入: 每个场景的 visual_prompt              │
│  输出: 5-8张分镜图 + 镜头语言标注             │
└──────────────────┬───────────────────────────┘
                   │ Images + motion_prompts
                   ▼
┌──────────────────────────────────────────────┐
│  Stage 3: 🎥 Videographer（摄像师）          │
│  模型: RunwayML Gen-3 / Pika / Sora（视频模型）│
│  输入: 分镜图 + 动效提示词                   │
│  输出: 视频片段（每个场景一段）               │
└──────────────────┬───────────────────────────┘
                   │ Video clips
                   ▼
              🎉 最终成片
```

**设计模式**：顺序管道（Pipeline），知识库 Multi-Agent 四大协作模式之一。每个阶段的输出是下一个阶段的输入，阶段之间通过标准化数据结构解耦。

---

## 📂 项目结构

```
ai-video-studio/
│
├── config.py                         # 三个模型的独立配置
├── requirements.txt                  # Python 依赖
├── .env.example                      # API Key 模板
│
├── src/
│   ├── models/
│   │   └── __init__.py               # 📡 模型客户端层
│   │       ├── LLMClient             #    推理模型 (Stage 1)
│   │       ├── ImageGenClient        #    图像模型 (Stage 2)
│   │       ├── VideoGenClient        #    视频模型 (Stage 3)
│   │       └── 数据结构              #    Script → Scene → Shot → VideoClip
│   │
│   ├── agents/
│   │   ├── director.py               # 🎬 Stage 1: 剧本导演
│   │   │   ├── 系统提示词（严格JSON格式）
│   │   │   ├── 真实API模式
│   │   │   └── Mock模式（模板化剧本）
│   │   ├── storyboard.py             # 🎨 Stage 2: 分镜师
│   │   │   ├── 真实API模式（DALL-E等）
│   │   │   └── Mock模式（Pillow占位图）
│   │   └── videographer.py           # 🎥 Stage 3: 摄像师
│   │       ├── 真实API模式（Runway等）
│   │       └── Mock模式（静态帧+元数据）
│   │
│   ├── pipeline/
│   │   └── pipeline.py               # 🔗 编排器（核心）
│   │       ├── produce()              #    全流程一键执行
│   │       ├── step1/2/3()           #    分步执行（调试用）
│   │       └── 产出持久化            #    剧本JSON + 分镜PNG + 视频元数据
│   │
│   └── cli/
│       └── app.py                     # 💻 命令行交互界面
│
├── examples/
│   └── demo.py                        # 🚀 一键体验（Mock模式，无需API Key）
│
└── output/                            # 📁 产出目录
    ├── scripts/                       #    剧本 JSON
    ├── storyboard/                    #    分镜图 PNG
    ├── video/                         #    视频片段 / 元数据
    └── productions.json               #    制作记录
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd ai-video-studio
pip install -r requirements.txt
```

### 2. 体验 Mock 模式（无需任何 API Key）

```bash
python examples/demo.py
```

自动运行两个 Demo：小猫东京冒险 + 宇航员火星奇遇，输出剧本/分镜/视频元数据到 `output/` 目录。

### 3. 配置真实 API

```bash
cp .env.example .env
# 编辑 .env，填入三个模型的 API Key

# 导演模型（必填）
DIRECTOR_API_KEY=sk-your-openai-key
DIRECTOR_MODEL=gpt-4o

# 图像模型（可选）
IMAGE_API_KEY=sk-your-dalle-key
IMAGE_MODEL=dall-e-3

# 视频模型（可选，目前API接入中）
VIDEO_API_KEY=your-runway-key
VIDEO_MODEL=runway-gen3
```

### 4. 运行完整流水线

```bash
python -m src.cli.app
```

---

## 🎮 使用方式

### CLI 交互模式

```bash
python -m src.cli.app
```

```
🎬 AI 视频工作室
─────────────────────────────
选择视觉风格:
  1. cinematic  电影感
  2. anime      日式动漫
  3. 3d         3D 渲染
  4. watercolor 水彩画风
  ...

💡 输入你的视频创意: 一只狐狸在雨夜的城市天台拉小提琴
使用 Mock 模式？: y

🎬 [Director] 生成剧本...  5个场景
🎨 [Storyboard] 生成分镜... 5张图
🎥 [Videographer] 生成视频... 5个片段
🎉 制作完成！
```

### Python API 调用

```python
from src.pipeline.pipeline import VideoPipeline

# 完整流水线
pipeline = VideoPipeline(
    director_model="gpt-4o",
    use_mock=True,  # 无API Key时用Mock模式
)

production = pipeline.produce(
    idea="一只猫在太空站冒险",
    style="anime",
)

print(production.progress_report())
# 剧本✅ → 分镜✅ → 视频✅

# 分步执行（调试用）
script = pipeline.step1_script("一个孤独的机器人照顾最后一片森林")
storyboard = pipeline.step2_storyboard(script)
clips = pipeline.step3_video(storyboard)
```

---

## 🔌 支持的模型

### Stage 1: 推理模型（剧本生成）

| 模型 | 特点 | 配置 |
|------|------|------|
| **GPT-4o** | 创意最佳，指令遵循好 | `DIRECTOR_MODEL=gpt-4o` |
| **DeepSeek-R1** | 推理能力强，免费额度多 | `DIRECTOR_MODEL=deepseek-reasoner` |
| **Claude 3.5 Sonnet** | 长文本连贯性好 | `DIRECTOR_MODEL=claude-3-5-sonnet` |
| **DeepSeek-V3** | 中文理解优秀 | `DIRECTOR_MODEL=deepseek-chat` |

### Stage 2: 图像生成模型（分镜图）

| 模型 | 特点 | 配置 |
|------|------|------|
| **DALL-E 3** | 自然语言理解最强 | `IMAGE_MODEL=dall-e-3` |
| **Stable Diffusion XL** | 可控性最好 | 需 Replicate/Fal.ai API |
| **Midjourney** | 艺术性最好 | 需第三方 API 封装 |

### Stage 3: 视频生成模型（成片）

| 模型 | 特点 | 状态 |
|------|------|------|
| **RunwayML Gen-3** | 图生视频质量最高 | API 接入中 |
| **Pika Labs** | 性价比高 | API 接入中 |
| **Kling (可灵)** | 国产，中文好 | API 接入中 |

---

## 🎯 设计亮点

### 1. 标准化中间格式

每个阶段输出强类型的 `dataclass`——Stage 1 产 `Script`，Stage 2 产 `Storyboard`，Stage 3 产 `VideoClip`。任意阶段可独立替换模型，不影响上下游。

### 2. Mock 模式

每个 Agent 都内置 Mock 实现——开发调试无需任何 API Key：
- Director：模板化剧本（起承转合 5 段式）
- Storyboard：Pillow 生成带标注的占位图
- Videographer：复制分镜图 + JSON 元数据

### 3. Director 提示词工程

系统提示词精确定义了 JSON Schema 输出格式 + 创作约束：
- `visual_prompt` 用英文（DALL-E 等图像模型对英文理解更好）
- `motion_prompt` 用中文（动效描述更直观）
- 最后一个场景必须有"记忆点"

---

## 📚 相关知识库资料

| 知识库文档 | 对应内容 |
|-----------|---------|
| `Java手册/06-AI与Agent/10-Multi-Agent多智能体.md` | 顺序管道模式 |
| `Java手册/06-AI与Agent/06-Prompt工程.md` | Director 提示词设计 |
| `Java手册/06-AI与Agent/01-Agent核心概念.md` | Agent 架构基础 |
| `经验笔记/AI-Agent/多模型协作-视频工作室.md` | 本项目构建经验 |

---

## 📋 与同系列项目的关系

| 项目 | 模式 | Agent 数 | 适用场景 |
|------|------|---------|---------|
| `ai-agent-starter` (Python) | 单 Agent + 工具 | 1 | 学习 Agent 基础 |
| `ai-agent-java` (Java) | 单 Agent + 工具 | 1 | Java 集成 AI |
| `ai-video-studio` ⭐ | **多 Agent 管道** | 3 | 多模型协作 |
