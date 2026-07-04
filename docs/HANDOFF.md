# AI Video Studio — 项目交接文档

> 最后更新: 2026-07-05 | 当前版本: 重构后桌面端

## 项目位置

```
E:\AI项目\ai-video-studio\
```

## GitHub

```
https://github.com/pj-mmsn/ai-video-studio
```

## 当前状态

**桌面端小说家** (`src/desktop/novelist_qt.py`) 是主力，约500行，可以跑通完整流程。

**启动命令**:
```bash
cd E:\AI项目\ai-video-studio
python -m src.desktop.novelist_qt
```

## 当前架构

```
三个模式（左侧按钮切换）:
  💡 构思 → AI生成梗概+角色+世界观
  📋 大纲 → AI生成卷/章/节结构（每节带概要）
  ✍️ 写作 → 点击左侧大纲某节 → 执行 → AI写正文

右侧四个标签:
  当前内容（构思/大纲/正文都在这展示）
  角色
  世界观
  大纲树（目录）

LLM调用:
  构思: 流式（StreamThread + chat_stream）
  大纲: 流式 + 非流式fallback
  写作: 非流式（chat()，避免deepseek-v4-pro的thinking块污染）

数据库:
  output/novels/<项目ID>/novel.db（9张表）
  启动时自动扫描已有项目，可新建或继续

模型:
  默认 deepseek-v4-pro @ https://api.deepseek.com/anthropic
  .env里配 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
```

## 关键文件

| 文件 | 作用 |
|------|------|
| `src/desktop/novelist_qt.py` | PyQt5桌面端，主要代码 |
| `src/models/llm_client.py` | chat() + chat_stream()，支持Anthropic SSE |
| `src/db/novel_repository.py` | SQLite CRUD + 智能上下文检索 |
| `src/agents/novelist.py` | 小说家Agent（CLI用） |
| `config.py` | load_config() 函数式配置 |
| `.env` | API Key配置 |

## 已知问题

1. **deepseek-v4-pro thinking块**: 写作模式必须用非流式 `chat()`，流式会混入thinking内容
2. **滚动条**: 右侧面板用QScrollArea包裹了，理论上可见
3. **语法**: 当前 Python AST 检查通过，0报错
4. **项目加载**: 启动弹窗可扫描已有项目并恢复数据

## 上次操作

```
1. 右侧面板QTextBrowser→QTextEdit→QScrollArea包裹（滚动条问题）
2. 写作模式改用非流式chat()调用
3. _clean_output()清洗LLM输出的JSON前缀
4. 大纲每节带概要 + 写作时注入整章结构到上下文
5. 构思/大纲/写作三种模式发给模型的提示词已区分
```

## 下一步可做

1. 导演Agent接续：小说写完 → 改编为剧本 → 分镜 → 视频
2. Web可视化面板：`src/workflow/` 已有工作流引擎
3. 接入即梦/Kling等视频生成API
4. 多项目导出/版本管理
