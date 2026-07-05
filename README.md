# ✍️ AI 小说家 — 桌面端智能写作工具
<img width="1322" height="882" alt="image" src="https://github.com/user-attachments/assets/a4af7994-f9b4-45ae-9a1c-7f5485660bd3" />


> PyQt5 桌面应用，AI 驱动的长篇小说创作助手。从构思到成稿，五步流水线。

[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green)](https://www.riverbankcomputing.com/software/pyqt/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek%20V4%20Pro-purple)](https://api.deepseek.com)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

---

## 🎯 概述

**五模式 AI 写作流水线**：💡构思 → 📋大纲 → ✍️写作 → 📝修订 → 🔍审稿

选择模型、输入想法，AI 帮你完成从世界观构建到逐节写作的全过程。支持断点续写、角色管理、全文导出。

### 界面预览

```
┌──────────┬────────────────────┬───────────────┐
│  💡 构思  │   📘 第1卷 火种觉醒   │  当前内容      │
│  📋 大纲  │    📄 第1章 废墟..   │  角色          │
│  ✍️ 写作  │     📝 第1节 ✓     │  世界观        │
│  🔍 审稿  │     📝 第2节 ✓     │  大纲(可编辑)   │
│  📥 导出  │    📄 第2章 基因..   │  全文          │
│          │   📘 第2卷 霸权..   │               │
│  模型▾   │                    │               │
│          │  [修改意见...]      │               │
│          │  [执行] [✏编辑]    │               │
└──────────┴────────────────────┴───────────────┘
```

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env → 填 LLM_API_KEY

# 3. 启动
python -m src.desktop.novelist_qt
```

**.env 最小配置**：
```env
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.deepseek.com/anthropic
LLM_MODEL=deepseek-v4-pro
LLM_MODEL_LIGHT=deepseek-v4-flash   # 审稿用（可选）
```

---

## 🏗️ 架构

### 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| UI | PyQt5 | 单窗口多面板桌面应用 |
| LLM | DeepSeek V4 Pro/Flash | Anthropic 兼容 API，流式+非流式 |
| DB | SQLite | 单文件，平铺表设计，9 张表 |
| 配置 | python-dotenv | .env 动态读取 |
| 代码量 | ~3200 行 | 纯 Python + 标准库 |

### 数据流

```
┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
│ 💡构思  │→  │ 📋大纲  │→  │ ✍️写作  │→  │ 📝修订  │→  │ 🔍审稿  │
└───┬────┘   └───┬────┘   └───┬────┘   └───┬────┘   └───┬────┘
    │            │            │            │            │
    ▼            ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────┐
│                   LLM Client (chat/chat_stream)              │
│            https://api.deepseek.com/anthropic                │
│                   1M Token 上下文窗口                         │
└─────────────────────────────────────────────────────────────┘
    │            │            │            │            │
    ▼            ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────┐
│                    SQLite (novel.db)                         │
│  novels │ outline_nodes │ sections │ characters │ reviews   │
└─────────────────────────────────────────────────────────────┘
```

### 写作时发给模型的上下文

```
┌─ System Prompt ────────────────────────┐
│ 你是职业小说家。从【前情提要】结尾接续...   │
└────────────────────────────────────────┘
┌─ User Prompt ──────────────────────────┐
│ 【大纲】 本章结构 + 当前节概要           │
│ 【前情提要】 前卷全文 + 当前卷已写内容     │
│ （角色设定 + 世界观）                    │
│ 【原文】 仅修订模式                      │
│ 【修改意见】 有反馈时                     │
└────────────────────────────────────────┘
```

---

## 📂 项目结构

```
ai-video-studio/
├── .env                          # API Key（gitignore）
├── config.py              (35L)  # 配置加载
├── requirements.txt
│
├── src/
│   ├── desktop/                  # ⭐ 桌面端小说家（主力）
│   │   ├── novelist_qt.py (1802L) # 主窗口：五模式 + UI
│   │   ├── theme.py       (132L)  # 配色 + 样式工厂
│   │   ├── prompts.py     (202L)  # 5 种 System Prompt
│   │   └── utils.py       (368L)  # 清洗/解析/导出/上下文
│   │
│   ├── db/
│   │   └── novel_repository.py (507L) # SQLite CRUD + 迁移
│   │
│   ├── models/
│   │   └── llm_client.py  (146L)  # chat() + chat_stream()
│   │
│   ├── agents/                    # 视频管线 Agent（独立模块）
│   │   ├── director.py           # 剧本导演
│   │   ├── storyboard.py         # 分镜师
│   │   └── videographer.py       # 摄像师
│   │
│   └── pipeline/
│       └── pipeline.py            # 视频制作编排器
│
├── docs/
│   └── HANDOFF.md                 # 项目交接文档
│
└── output/novels/<项目ID>/
    └── novel.db                   # SQLite 数据库
```

---

## 🎯 核心特性

### 五模式写作流水线

| 模式 | 功能 | 模型推荐 |
|------|------|:--:|
| 💡 **构思** | 想法→完整世界观+角色（JSON） | Pro |
| 📋 **大纲** | 卷→章→节三级结构（每节带概要） | Pro |
| ✍️ **写作** | 上下文驱动逐节创作（800-2000字） | Pro |
| 📝 **修订** | 反馈驱动精准修改（决策表判断范围） | Pro |
| 🔍 **审稿** | 全文对照大纲检查差异+连贯性 | Flash |

### 上下文策略

- **1M Token 窗口**：前卷全文 + 当前卷已写内容全塞入
- **接续锚点**：上下文末尾标注上一节结尾段落，引导模型精准接续
- **角色+世界观注入**：每节写作时自动附带角色设定和世界观约束

### 大纲管理

- 平铺表设计（volume_title + chapter_title + section_order），不用自引用树
- 全局章节编号顺延（卷 2 第 1 章→第 5 章）
- 右键菜单：改标题/改概要/标记完成/删除
- "大纲"标签页：全文可编辑，切换标签自动保存
- 批量替换：一键替换大纲中所有文本

### 角色管理

- 独立的角色编辑面板（名/身份/性格/欲望/恐惧）
- 增删改查 + DB 持久化
- 构思阶段 AI 自动生成角色

### 全文导出

- TXT：纯净文本，卷章层级标题
- HTML：深色主题 + 目录 + 排版

### 其他

- 🔄 断点续写：关闭后重新打开，大纲和已写内容完整保留
- 🎨 深色主题：Tokyo Night 配色
- ⌨️ 键盘快捷键：Ctrl+Enter 执行、Ctrl+F 搜索、Ctrl+E 导出
- 📊 实时进度：已完成节数、总字数
- 🖨️ 终端打印：每次 LLM 调用打印完整 system/user prompt
- 🔀 模型切换：侧边栏下拉框随时切换 Pro/Flash

---

## 🛠️ 开发要点

### 数据库设计：树形 → 平铺

```sql
-- 旧设计（自引用树）：查询递归、孤儿数据
CREATE TABLE nodes (id, parent_id, level, title);

-- 新设计（平铺三列）：一条 ORDER BY 搞定
CREATE TABLE nodes (
  volume_title  TEXT,    -- 卷名
  chapter_title TEXT,    -- 章名
  section_order INTEGER, -- 第几节
  section_title TEXT,    -- 节标题
  sort_order    INTEGER  -- 全局排序（铁律：永远用整数排）
);
```

### Prompt 工程经验

1. **Few-shot 示例**：格式合规率 ~60% → ~95%
2. **首尾效应**：最重要约束放第一句和最后一句
3. **标签对齐**：System Prompt 和 User Prompt 用相同的 `【标签】` 格式
4. **接续锚点**：上下文末尾标注上一节结尾，引导精准接续
5. **决策表代替模糊指令**：用"如果A→做X"替代"尽量少改"

### 关键踩坑

- **同步调用卡死 UI**：改用 `QThread` + `chat_stream()` 流式
- **LEFT JOIN 返回旧版本**：`save_section` 改用 UPDATE OR INSERT
- **字母序排序错误**："第10章"排在"第2章"前 → 加 `sort_order` 整数列
- **迁移覆盖排序**：每次启动重排 sort_order → 改为仅首次迁移

---

## 🔮 路线图

- [x] 五模式写作流水线
- [x] 角色管理 + 全文导出
- [x] 大纲可编辑 + 批量替换
- [x] 审稿模式（全文对照大纲）
- [x] 上下文策略优化（1M 窗口 + 接续锚点）
- [ ] 接入视频生成 API（即梦/Kling）
- [ ] Vector DB 角色/伏笔检索（长篇 >10 卷）
- [ ] 多 Agent 协作（导演→分镜→摄像师）

---

## 📚 相关知识库

| 位置 | 内容 |
|------|------|
| `Java手册/06-AI与Agent/06-Prompt工程` | Prompt 设计原理 + 实战经验 |
| `Java手册/06-AI与Agent/05-RAG` | 1M 上下文 vs RAG 决策 |
| `Java手册/06-AI与Agent/03-记忆系统` | 平铺表设计 + sort_order 铁律 |
| `Java手册/06-AI与Agent/10-Multi-Agent` | MCP/A2A 协议 + 单体够用判断 |
| `经验笔记/AI-Agent/项目实战/AI小说家.md` | 本项目完整踩坑记录 |
| `经验笔记/AI-Agent/Prompt工程实战.md` | 5 条 Prompt 设计经验 |

---

## 📄 License

MIT
