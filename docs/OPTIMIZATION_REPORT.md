# AI Video Studio 优化分析报告

> 基线：v1.0（8 文件，1237 行）→ v2.0（13 文件，~2100 行）  
> 审查日期：2026-07-04 | GitHub: https://github.com/pj-mmsn/ai-video-studio

---

## 一、优化清单

| # | 优化项 | 优先级 | 文件 |
|---|--------|:--:|------|
| 1 | Mock 剧本模板化（从用户idea提取关键词动态填充） | P0 | `agents/director.py` |
| 2 | 视频合成（moviepy 合成 MP4 + 硬字幕） | P0 | `tools/composer.py` |
| 3 | 旁白生成（edge-tts 将dialogue转语音） | P0 | `tools/composer.py` |
| 4 | 日志系统（print→logging, 控制台+文件） | P1 | `logging_config.py` |
| 5 | CLI 命令行参数（--idea --style --mock --resume） | P1 | `cli/app.py` |
| 6 | SQLite 持久化（6表, 断点续传, 进度查询） | P0 | `db/schema.py` `db/repository.py` |
| 7 | StoryBible 上下文（LLM提取角色/地点/道具, 跨场景一致） | P0 | `context/bible.py` |
| 8 | Reviewer 审查（CrewAI反馈循环, 不合格重试） | P0 | `agents/reviewer.py` |
| 9 | Few-shot Prompt（2个完整参考剧本, 提升输出质量） | P0 | `agents/director.py` |

---

## 二、优化前后对比

| 维度 | v1.0 | v2.0 |
|------|------|------|
| 架构 | 线性3阶段 | 4阶段 + 审查反馈循环 |
| 持久化 | JSON文件 | SQLite（每项目独立DB） |
| 断点续传 | ❌ | ✅ 自动检测+恢复 |
| 跨场景一致 | ❌ 场景50不记得场景1 | ✅ StoryBible自动追踪 |
| 视频产出 | PNG + JSON元数据 | MP4（或降级图片序列） |
| 旁白字幕 | ❌ dialogue被丢弃 | ✅ edge-tts + 硬字幕 |
| Mock质量 | 固定模板 | 动态提取关键词填充 |
| 日志 | print() | logging（控制台+文件） |
| CLI | 仅交互式 | 交互式 + 命令行参数 |

---

## 三、Pipeline 完整流程

```
用户输入 → DB初始化 + 断点检测
    ↓
Stage 1: Director（LLM + StoryBible上下文 + Few-shot）
    → Script → scenes表 → 🔍Review → 📖Bible提取
    ↓
Stage 2: Storyboard（DALL-E/SD）
    → Shots → shots表 → 🔍Review
    ↓
Stage 3: Videographer（Runway/Pika）
    → Clips → clips表 → 🔍Review
    ↓
Stage 4: Composer（moviepy/ffmpeg）
    → video.mp4 + subtitle.srt
    ↓
🎉 最终输出
```

---

## 四、使用方式

```bash
# 命令行模式
python -m src.cli.app --idea "猫在太空站" --style anime --mock

# 断点续传
python -m src.cli.app --resume proj_1234567890

# 完整模式
python -m src.cli.app --idea "赛博朋克爱情" --style cinematic --strictness 8

# 交互模式
python -m src.cli.app
```
