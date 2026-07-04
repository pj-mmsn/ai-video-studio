"""
智能上下文构建器 — 借鉴 ZCode 分层压缩策略
============================================================
ZCode 的做法:
  - 最近的消息保留原文（高保真）
  - 旧的消息压缩为摘要（低保真，省 token）
  - 关键信息（角色/设定）永远不压缩

我们的实现:
  Tier 1 (原文): 当前节大纲 + 上一节完整内容
  Tier 2 (摘要): 前 2-5 节摘要
  Tier 3 (压缩): 更早的内容 → 一句话概要
  Tier 4 (永存): 角色设定 + 核心世界观（永不压缩）

每次拼 prompt:
  [永存] → [Tier3概要] → [Tier2摘要] → [Tier1原文] → 组装发送
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from src.db.studio_db import StudioDB
from src.db.session_store import SessionStore


@dataclass
class ContextTier:
    """分层上下文"""
    frozen: dict        # 永存: 角色/世界观（不压缩）
    hot: str            # 原文: 上一节完整内容
    warm: list[str]     # 摘要: 前2-5节摘要
    cold: list[str]     # 压缩: 更早内容的一句话概要

    def estimate_tokens(self) -> int:
        total = len(json.dumps(self.frozen, ensure_ascii=False)) // 2
        total += len(self.hot) // 2
        total += sum(len(s) // 2 for s in self.warm)
        total += sum(len(s) // 2 for s in self.cold)
        return total

    def to_prompt(self) -> str:
        """拼成发给 LLM 的最终文本"""
        parts = []

        # Tier 4: 永存——角色和世界观（最重要）
        frozen_parts = []
        chars = self.frozen.get("characters", [])
        if chars:
            frozen_parts.append("## 角色设定（严格遵循）")
            for c in chars[:10]:  # 最多10个角色
                frozen_parts.append(f"- {c.get('name','')}({c.get('role','')}): {c.get('traits','')}")

        rules = self.frozen.get("world_rules", [])
        if rules:
            frozen_parts.append("\n## 世界观约束")
            for r in rules[:5]:
                frozen_parts.append(f"- {r.get('key','')}: {r.get('value','')}")

        threads = self.frozen.get("open_threads", [])
        if threads:
            frozen_parts.append("\n## 待推进剧情线")
            for t in threads[:5]:
                frozen_parts.append(f"- [{t.get('tags','主线')}] {t.get('description','')}")

        if frozen_parts:
            parts.append("\n".join(frozen_parts))

        # Tier 3: 压缩——早期内容一句话带过
        if self.cold:
            parts.append("\n## 前期回顾\n" + "\n".join(f"- {s}" for s in self.cold))

        # Tier 2: 摘要——最近的章节摘要
        if self.warm:
            parts.append("\n## 最近章节\n" + "\n".join(f"- {s}" for s in self.warm))

        # Tier 1: 原文——上一节的完整内容
        if self.hot:
            parts.append(f"\n## 上一节原文\n{self.hot}")

        return "\n\n".join(parts)


class SmartContextBuilder:
    """智能上下文构建器"""

    def __init__(self, db: StudioDB, session: SessionStore):
        self.db = db
        self.session = session

    def build(self, current_node_id: int, max_tokens: int = 4000) -> ContextTier:
        """构建分层上下文，优先保留重要信息"""

        # Tier 4: 永存——从 SQL 取,永不压缩
        frozen = {
            "characters": self.db.get_bible("character"),
            "world_rules": self.db.get_bible("world_rule"),
            "open_threads": [t for t in self.db.get_bible("plot_thread")
                           if t.get("status") == "open"],
        }

        # 从 Redis 获取会话上下文
        ctx = self.session.get_context()

        # Tier 1: 原文——上一节
        hot = ""
        sections = self.db.get_sections()
        if sections:
            latest = sections[-1]
            hot = latest.get("content", "")[-1500:]  # 只取最后1500字

        # Tier 2: 摘要——最近章节
        warm = ctx.get("recent_summaries", [])[-3:]

        # Tier 3: 压缩——更早的一两句话概括
        cold = ctx.get("recent_summaries", [])[:-3]
        cold = [s[:80] + "..." if len(s) > 80 else s for s in cold]

        tier = ContextTier(frozen=frozen, hot=hot, warm=warm, cold=cold)
        tokens = tier.estimate_tokens()

        # 超限时逐层裁剪（从最不重要的开始）
        while tokens > max_tokens:
            if cold:
                cold.pop(0)  # 先扔掉冷数据
            elif len(warm) > 1:
                warm.pop(0)  # 再减少摘要
            elif len(hot) > 500:
                hot = hot[-500:]  # 缩短原文
            else:
                break  # 裁无可裁
            tier = ContextTier(frozen=frozen, hot=hot, warm=warm, cold=cold)
            tokens = tier.estimate_tokens()

        return tier
