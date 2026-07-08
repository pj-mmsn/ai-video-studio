"""
Novelist Agent — 交互式小说创作
============================================================
独立启动: python -m src.cli.novelist

工作模式: 交互式协作写作
  你给灵感和方向 → AI 写 → 你纠正 → AI 修改 → 继续下一章

命令:
  /write      - 开始/继续写当前章节
  /rewrite    - 重写当前章节
  /outline    - 查看/修改大纲
  /characters - 查看/修改角色设定
  /continue   - 继续下一章
  /revise <意见> - 根据意见修改当前内容
  /summary    - 查看故事概要
  /save       - 保存到文件
  /quit       - 退出
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.models import LLMClient
from src.logging_config import info, debug


# ================================================================
# 小说家系统提示词
# ================================================================

NOVELIST_SYSTEM = """你是一位职业小说家，擅长多种类型：玄幻、科幻、都市、悬疑、言情、历史。

## 写作风格
- 文字有画面感，擅长场景描写和人物心理刻画
- 对话自然生动，符合角色性格
- 节奏张弛有度：紧张段落短句快节奏，抒情段落细腻描写
- 每章结尾留悬念或情感钩子

## 交互规则
1. 用户会给你反馈/修改意见，请认真对待并修改
2. 如果用户说"这段不行/换一种写法"，不要辩解，直接重写
3. 保持前后一致：角色性格、世界观设定、剧情线索不能冲突
4. 如果用户要求修改已写好的内容，修改后确认

## 输出格式
【第X章 标题】
（正文内容，每章 1000-3000 字）

写完后附上：
---
📝 本章要点：一句话总结
🔮 下章预告：一句话预告"""


# ================================================================
# 数据模型
# ================================================================

@dataclass
class Character:
    name: str
    role: str           # 主角/配角/反派
    description: str    # 外貌、性格、背景
    notes: str = ""


@dataclass
class Chapter:
    number: int
    title: str
    content: str
    summary: str = ""
    next_hint: str = ""


@dataclass
class Novel:
    title: str
    genre: str
    premise: str                        # 一句话梗概
    outline: list[str] = field(default_factory=list)  # 章节大纲
    characters: list[Character] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    world_building: str = ""            # 世界观设定


# ================================================================
# 小说家 Agent
# ================================================================

class NovelistAgent:
    """交互式小说创作 Agent"""

    def __init__(self, config: dict = None):
        from app.config import load_config
        self.config = config or load_config()

    def _chat(self, system: str, user: str) -> str:
        from src.models.llm_client import chat
        return chat(self.config, system, user)

    # ---------------------------------------------------------------
    # 初始化：设定世界观
    # ---------------------------------------------------------------

    def init_novel(self, idea: str, genre: str = "玄幻") -> Novel:
        """根据灵感初始化小说框架"""
        prompt = f"""请根据以下灵感，构思一部{genre}小说的基础框架。用 JSON 格式返回。

灵感: {idea}

返回格式:
{{
  "title": "小说标题",
  "premise": "一句话梗概（50字内）",
  "outline": ["第1章 大纲", "第2章 大纲", ...],
  "world_building": "世界观简述（100字内）",
  "characters": [
    {{"name": "角色名", "role": "主角/配角/反派", "description": "外貌性格背景", "notes": "补充"}}
  ]
}}"""

        info(f"📖 正在构思小说框架...")
        raw = self._chat(NOVELIST_SYSTEM, prompt)

        data = self._parse_json(raw)
        self.novel = Novel(
            title=data.get("title", f"《{idea[:20]}》"),
            genre=genre,
            premise=data.get("premise", ""),
            outline=data.get("outline", []),
            world_building=data.get("world_building", ""),
            characters=[Character(**c) for c in data.get("characters", [])],
        )

        self._print_novel_info()
        return self.novel

    # ---------------------------------------------------------------
    # 写作
    # ---------------------------------------------------------------

    def write_chapter(self, chapter_num: int = None) -> Chapter:
        """写/续写一章"""
        if self.novel is None:
            raise RuntimeError("请先 init_novel() 初始化小说")

        num = chapter_num or len(self.novel.chapters) + 1
        outline_text = self.novel.outline[num - 1] if num <= len(self.novel.outline) else "自由发挥"

        # 构建上下文
        context = self._build_context(num)

        prompt = f"""请写第{num}章。

大纲指引: {outline_text}

{context}

要求: 1000-3000字，有画面感，结尾留钩子。"""

        info(f"✍️  正在写第{num}章...")
        raw = self._chat(NOVELIST_SYSTEM, prompt)

        # 解析章节内容
        title, content, summary, hint = self._parse_chapter(raw, num)

        chapter = Chapter(number=num, title=title, content=content,
                         summary=summary, next_hint=hint)
        self.novel.chapters.append(chapter)
        self.current_chapter = num

        info(f"   ✅ 第{num}章完成: {title} ({len(content)}字)")
        return chapter

    def rewrite_chapter(self, feedback: str = "") -> Chapter:
        """根据反馈重写当前章节"""
        if not self.novel.chapters:
            return self.write_chapter(1)

        ch = self.novel.chapters[-1]
        prompt = f"""请重写第{ch.number}章。

原标题: {ch.title}
原内容:
{ch.content[:500]}...

反馈意见: {feedback if feedback else "请换一种写法，保持剧情走向但改变叙事角度或细节"}

要求: 保持剧情走向不变，但根据反馈调整。"""

        info(f"🔄 正在重写第{ch.number}章...")
        raw = self._chat(NOVELIST_SYSTEM, prompt)

        title, content, summary, hint = self._parse_chapter(raw, ch.number)
        ch.title = title
        ch.content = content
        ch.summary = summary
        ch.next_hint = hint

        info(f"   ✅ 重写完成")
        return ch

    def revise_content(self, instruction: str) -> str:
        """局部修改——不改整章，只改指定部分"""
        if not self.novel.chapters:
            return "还没有内容可修改"

        ch = self.novel.chapters[-1]
        prompt = f"""当前第{ch.number}章内容:
{ch.content}

修改要求: {instruction}

请输出修改后的完整章节。只修改指定的部分，其余保持不变。"""

        info(f"🔧 正在修改...")
        raw = self._chat(NOVELIST_SYSTEM, prompt)
        ch.content = raw
        info(f"   ✅ 修改完成")
        return raw

    # ---------------------------------------------------------------
    # 上下文构建
    # ---------------------------------------------------------------

    def _build_context(self, chapter_num: int) -> str:
        """构建写作上下文——让 LLM 知道之前发生了什么"""
        parts = []

        # 小说基础信息
        parts.append(f"小说标题: {self.novel.title}")
        parts.append(f"类型: {self.novel.genre}")
        parts.append(f"梗概: {self.novel.premise}")

        # 世界观
        if self.novel.world_building:
            parts.append(f"\n世界观: {self.novel.world_building}")

        # 角色
        if self.novel.characters:
            parts.append("\n角色设定（请严格保持一致性）:")
            for c in self.novel.characters:
                parts.append(f"  - {c.name}({c.role}): {c.description}")

        # 已有章节摘要
        if self.novel.chapters:
            parts.append(f"\n前情提要（共{len(self.novel.chapters)}章）:")
            for ch in self.novel.chapters[-5:]:  # 最近5章
                parts.append(f"  第{ch.number}章《{ch.title}》: {ch.summary}")

        return "\n".join(parts)

    # ---------------------------------------------------------------
    # 解析
    # ---------------------------------------------------------------

    def _parse_chapter(self, raw: str, num: int) -> tuple[str, str, str, str]:
        """解析 LLM 输出的章节内容"""
        title = f"第{num}章"
        summary = ""
        hint = ""

        # 提取标题
        title_match = re.search(r'【第\d+章\s*(.+?)】', raw)
        if title_match:
            title = title_match.group(1)

        # 提取摘要和预告
        summary_match = re.search(r'📝\s*本章要点[：:]\s*(.+?)(?:\n|$)', raw)
        if summary_match:
            summary = summary_match.group(1)

        hint_match = re.search(r'🔮\s*下章预告[：:]\s*(.+?)(?:\n|$)', raw)
        if hint_match:
            hint = hint_match.group(1)

        # 正文：去掉标记行
        content = re.sub(r'【第\d+章.*?】', '', raw)
        content = re.sub(r'---.*', '', content)
        content = re.sub(r'[📝🔮].*', '', content).strip()

        return title, content, summary, hint

    def _parse_json(self, raw: str) -> dict:
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0]
        try:
            return json.loads(json_str.strip())
        except json.JSONDecodeError:
            return {}

    # ---------------------------------------------------------------
    # 显示
    # ---------------------------------------------------------------

    def _print_novel_info(self):
        print(f"\n{'='*50}")
        print(f"📖 {self.novel.title}")
        print(f"   类型: {self.novel.genre}")
        print(f"   梗概: {self.novel.premise}")
        print(f"\n📋 大纲 ({len(self.novel.outline)}章):")
        for i, o in enumerate(self.novel.outline, 1):
            print(f"   {i}. {o}")
        print(f"\n👥 角色 ({len(self.novel.characters)}人):")
        for c in self.novel.characters:
            print(f"   {c.name}({c.role}): {c.description[:60]}...")
        print(f"{'='*50}\n")

    def get_status(self) -> str:
        if not self.novel:
            return "尚未初始化小说"
        return (
            f"《{self.novel.title}》| {self.novel.genre}\n"
            f"进度: {len(self.novel.chapters)}/{len(self.novel.outline)}章\n"
            f"角色: {len(self.novel.characters)}人\n"
            f"总字数: {sum(len(c.content) for c in self.novel.chapters)}"
        )

    # ---------------------------------------------------------------
    # 保存
    # ---------------------------------------------------------------

    def save(self, path: str = None):
        if not self.novel:
            return
        path = path or f"output/novels/{self.novel.title.replace(' ', '_')}.txt"
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{self.novel.title}\n")
            f.write(f"类型: {self.novel.genre}\n")
            f.write(f"梗概: {self.novel.premise}\n")
            f.write(f"{'='*60}\n\n")

            for ch in self.novel.chapters:
                f.write(f"第{ch.number}章 {ch.title}\n")
                f.write(f"{'─'*40}\n")
                f.write(ch.content)
                f.write(f"\n\n")

        info(f"💾 已保存: {path}")
