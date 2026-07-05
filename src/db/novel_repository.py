"""
长篇小说数据库 — SQLite 上下文管理
============================================================
表设计见 docs/NOVEL_CONTEXT_DESIGN.md
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.logging_config import info, debug


class NovelRepository:
    """长篇小说持久化 + 智能上下文检索"""

    def __init__(self, novel_id: str, db_dir: str = None):
        self.novel_id = novel_id
        if db_dir is None:
            # 相对于项目根目录的绝对路径
            import os as _os
            _base = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
            db_dir = _os.path.join(_base, "output", "novels")
        db_path = Path(db_dir) / novel_id / "novel.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        self._lock = __import__('threading').Lock()  # 防止并发写入

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS novels (
                id TEXT PRIMARY KEY, title TEXT, genre TEXT,
                premise TEXT, status TEXT DEFAULT 'draft',
                total_words INTEGER DEFAULT 0,
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS outline_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id TEXT,
                volume_title TEXT DEFAULT '',
                chapter_title TEXT DEFAULT '',
                section_order INTEGER DEFAULT 0,
                section_title TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id TEXT, outline_node_id INTEGER,
                content TEXT, word_count INTEGER DEFAULT 0,
                summary TEXT, version INTEGER DEFAULT 1,
                created_at TEXT, updated_at TEXT,
                FOREIGN KEY(outline_node_id) REFERENCES outline_nodes(id)
            );
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id TEXT, name TEXT, role TEXT,
                traits TEXT, desire TEXT DEFAULT '', fear TEXT DEFAULT '',
                arc TEXT, notes TEXT,
                first_appearance_section INTEGER,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS character_scenes (
                character_id INTEGER, section_id INTEGER,
                role_in_scene TEXT,
                PRIMARY KEY(character_id, section_id)
            );
            CREATE TABLE IF NOT EXISTS world_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id TEXT, category TEXT, key TEXT, value TEXT,
                source_section INTEGER, tags TEXT
            );
            CREATE TABLE IF NOT EXISTS plot_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id TEXT, description TEXT,
                status TEXT DEFAULT 'open',
                introduced_section INTEGER,
                resolved_section INTEGER,
                tags TEXT, priority INTEGER DEFAULT 5
            );
            CREATE TABLE IF NOT EXISTS context_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id TEXT, section_id INTEGER,
                context_json TEXT, token_estimate INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS story_bible (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT, category TEXT, key TEXT, value TEXT,
                source_scene INTEGER DEFAULT 0, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id TEXT, content TEXT, created_at TEXT
            );
        """)
        self.conn.commit()
        self._migrate_outline()
        self._migrate_characters()

    def _migrate_outline(self):
        """迁移旧数据：从 parent_id/level/title 树结构填充新的平铺列"""
        import re

        def clean_title(t, label):
            """清洗标题：只去掉AI自己加的冗余前缀，保留我们的编号
            例: "第1卷 第一卷：火种觉醒" → "第1卷 火种觉醒"
                "第5章 第三章：辐射巢穴" → "第5章 辐射巢穴"
            """
            if not t: return ""
            # 匹配模式：我们的编号(AI的冗余编号)：实际名称
            # 我们的编号：第\d+卷/章 (如 "第1卷", "第5章")
            # AI冗余编号：第[中文数字]+卷/章[：:] (如 "第一卷：", "第三章：")
            m = re.match(r'^(第\d+[卷章])\s*第[一二三四五六七八九十\d]+[卷章][：:\s]*(.*)', t)
            if m:
                return f"{m.group(1)} {m.group(2).strip()}"
            return t
        # 添加新列（如果旧表没有）
        try:
            self.conn.execute("ALTER TABLE outline_nodes ADD COLUMN volume_title TEXT DEFAULT ''")
        except: pass
        try:
            self.conn.execute("ALTER TABLE outline_nodes ADD COLUMN chapter_title TEXT DEFAULT ''")
        except: pass
        try:
            self.conn.execute("ALTER TABLE outline_nodes ADD COLUMN section_order INTEGER DEFAULT 0")
        except: pass
        try:
            self.conn.execute("ALTER TABLE outline_nodes ADD COLUMN section_title TEXT DEFAULT ''")
        except: pass
        try:
            self.conn.execute("ALTER TABLE outline_nodes ADD COLUMN sort_order INTEGER DEFAULT 0")
        except: pass

        # Step 1: 迁移旧数据（旧列可能已被删除，容错）
        try:
            count = self.conn.execute(
                "SELECT COUNT(*) FROM outline_nodes WHERE volume_title='' AND chapter_title='' AND section_title='' AND level='section'"
            ).fetchone()[0]
        except:
            count = 0
        if count > 0:
            print(f"  🔄 迁移 {count} 条旧大纲数据...")
            # 获取所有节点
            nodes = self.conn.execute("SELECT * FROM outline_nodes ORDER BY sort_order, id").fetchall()
            node_map = {n["id"]: dict(n) for n in nodes}

            # 为每个 section 找到其所属的卷和章
            for n in nodes:
                if n["level"] == "section":
                    vol_title = ""
                    ch_title = ""
                    sec_order = 0
                    sec_title = n["title"] or ""

                    # 往上找 chapter
                    pid = n["parent_id"]
                    while pid and pid in node_map:
                        parent = node_map[pid]
                        if parent["level"] == "chapter":
                            ch_title = clean_title(parent["title"] or "", "chapter")
                            break
                        pid = parent.get("parent_id")

                    # 往上找 volume
                    pid = n["parent_id"]
                    while pid and pid in node_map:
                        parent = node_map[pid]
                        if parent["level"] == "volume":
                            vol_title = clean_title(parent["title"] or "", "volume")
                            break
                        pid = parent.get("parent_id")

                    # 计算节序号（同一章内的排序）
                    if ch_title:
                        siblings = self.conn.execute(
                            "SELECT id FROM outline_nodes WHERE parent_id=? ORDER BY sort_order, id",
                            (n["parent_id"],)
                        ).fetchall()
                        for i, sib in enumerate(siblings):
                            if sib["id"] == n["id"]:
                                sec_order = i + 1
                                break

                    self.conn.execute(
                        "UPDATE outline_nodes SET volume_title=?, chapter_title=?, section_order=?, section_title=? WHERE id=?",
                        (vol_title, ch_title, sec_order, sec_title, n["id"])
                    )
                elif n["level"] == "chapter":
                    self.conn.execute(
                        "UPDATE outline_nodes SET chapter_title=? WHERE id=?",
                        (clean_title(n["title"] or "", "chapter"), n["id"])
                    )
                elif n["level"] == "volume":
                    self.conn.execute(
                        "UPDATE outline_nodes SET volume_title=? WHERE id=?",
                        (clean_title(n["title"] or "", "volume"), n["id"])
                    )

            self.conn.commit()
            print(f"  ✅ 迁移完成")

            # 填充 sort_order（按 id 保留原始插入顺序）
            all_rows = self.conn.execute(
                "SELECT id FROM outline_nodes WHERE section_title != '' ORDER BY id"
            ).fetchall()
            for i, r in enumerate(all_rows):
                self.conn.execute("UPDATE outline_nodes SET sort_order=? WHERE id=?", (i, r["id"]))
            self.conn.commit()

        # 清洗已有标题（去冗余前缀）
        existing = self.conn.execute(
            "SELECT id, volume_title, chapter_title FROM outline_nodes WHERE volume_title LIKE '第%卷%' OR chapter_title LIKE '第%章%'"
        ).fetchall()
        if existing:
            cleaned = 0
            for r in existing:
                new_vol = clean_title(r["volume_title"], "volume")
                new_ch = clean_title(r["chapter_title"], "chapter")
                if new_vol != r["volume_title"] or new_ch != r["chapter_title"]:
                    self.conn.execute(
                        "UPDATE outline_nodes SET volume_title=?, chapter_title=? WHERE id=?",
                        (new_vol, new_ch, r["id"])
                    )
                    cleaned += 1
            if cleaned:
                self.conn.commit()
                print(f"  🧹 清洗了 {cleaned} 条标题")

        # 删除旧列（SQLite 3.35+）
        try:
            self.conn.execute("ALTER TABLE outline_nodes DROP COLUMN parent_id")
        except: pass
        try:
            self.conn.execute("ALTER TABLE outline_nodes DROP COLUMN level")
        except: pass
        try:
            self.conn.execute("ALTER TABLE outline_nodes DROP COLUMN title")
        except: pass
        self.conn.commit()

    def _migrate_characters(self):
        """添加 desire/fear 列（如果旧表没有）"""
        for col in ["desire", "fear"]:
            try:
                self.conn.execute(f"ALTER TABLE characters ADD COLUMN {col} TEXT DEFAULT ''")
            except: pass

    # ================================================================
    # 大纲管理
    # ================================================================

    def create_outline(self, outline_data: list[dict]):
        """批量创建大纲节点 [{level, title, summary, parent_id?, sort_order}]"""
        for item in outline_data:
            self.conn.execute(
                """INSERT INTO outline_nodes (novel_id, parent_id, level, sort_order, title, summary, status)
                VALUES (?,?,?,?,?,?,?)""",
                (self.novel_id, item.get("parent_id"), item["level"],
                 item.get("sort_order", 0), item["title"],
                 item.get("summary", ""), "pending")
            )
        self.conn.commit()

    def get_outline_tree(self) -> list[dict]:
        """获取完整大纲树"""
        rows = self.conn.execute(
            "SELECT * FROM outline_nodes WHERE novel_id=? ORDER BY sort_order, id",
            (self.novel_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_node(self, node_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM outline_nodes WHERE id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    def update_node_status(self, node_id: int, status: str):
        self.conn.execute("UPDATE outline_nodes SET status=? WHERE id=?", (status, node_id))
        self.conn.commit()

    # ================================================================
    # 内容管理
    # ================================================================

    def save_section(self, node_id: int, content: str, summary: str = "",
                     new_characters: list[dict] = None,
                     new_threads: list[dict] = None,
                     new_rules: list[dict] = None) -> int:
        """保存一节内容（已存在则更新，否则新增）"""
        now = datetime.now().isoformat()
        word_count = len(content)

        # 检查是否已有记录
        existing = self.conn.execute(
            "SELECT id FROM sections WHERE outline_node_id=? ORDER BY id DESC LIMIT 1",
            (node_id,)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE sections SET content=?, word_count=?, summary=?, updated_at=? WHERE id=?",
                (content, word_count, summary, now, existing["id"])
            )
            section_id = existing["id"]
        else:
            cursor = self.conn.execute(
                """INSERT INTO sections (novel_id, outline_node_id, content, word_count, summary, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)""",
                (self.novel_id, node_id, content, word_count, summary, now, now)
            )
            section_id = cursor.lastrowid

        # 标记大纲节点为已完成
        self.update_node_status(node_id, "done")

        # 保存新角色
        if new_characters:
            for c in new_characters:
                self.conn.execute(
                    "INSERT INTO characters (novel_id, name, role, traits, arc, first_appearance_section, updated_at) VALUES (?,?,?,?,?,?,?)",
                    (self.novel_id, c["name"], c.get("role",""), c.get("traits",""),
                     c.get("arc",""), section_id, now)
                )
                # 关联出场
                char_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                self.conn.execute(
                    "INSERT INTO character_scenes (character_id, section_id, role_in_scene) VALUES (?,?,?)",
                    (char_id, section_id, c.get("role_in_scene", ""))
                )

        # 保存新伏笔
        if new_threads:
            for t in new_threads:
                self.conn.execute(
                    "INSERT INTO plot_threads (novel_id, description, status, introduced_section, tags, priority) VALUES (?,?,?,?,?,?)",
                    (self.novel_id, t["description"], "open", section_id,
                     t.get("tags", ""), t.get("priority", 5))
                )

        # 保存新世界观规则
        if new_rules:
            for r in new_rules:
                self.conn.execute(
                    "INSERT INTO world_rules (novel_id, category, key, value, source_section, tags) VALUES (?,?,?,?,?,?)",
                    (self.novel_id, r.get("category",""), r["key"], r["value"],
                     section_id, r.get("tags", ""))
                )

        # 更新总字数
        self.conn.execute(
            "UPDATE novels SET total_words = (SELECT COALESCE(SUM(word_count),0) FROM sections WHERE novel_id=?), updated_at=? WHERE id=?",
            (self.novel_id, now, self.novel_id)
        )
        self.conn.commit()
        return section_id

    # ================================================================
    # 智能上下文检索（核心）
    # ================================================================

    def get_writing_context(self, node_id: int, max_tokens: int = 4000) -> dict:
        """为写某一节构建精准上下文——只取需要的，不取全部

        Returns: {context_text, characters, threads, rules, recent_sections, token_estimate}
        """
        node = self.get_node(node_id)
        if not node:
            return {"context_text": "", "token_estimate": 0}

        parts = []
        token_est = 0

        # 1. 当前位置
        vol = node.get("volume_title", "")
        ch = node.get("chapter_title", "")
        sec = node.get("section_title", "")
        context_header = f"当前位置: {vol} > {ch} > 第{node.get('section_order',0)}节 {sec}\n概要: {node.get('summary','')}\n"
        parts.append(context_header)
        token_est += len(context_header) // 2

        # 2. 前情提要——最近3节的摘要 (~400 tokens)
        recent = self.conn.execute(
            "SELECT summary FROM sections WHERE novel_id=? ORDER BY id DESC LIMIT 3",
            (self.novel_id,)
        ).fetchall()
        if recent:
            recap = "前情提要:\n" + "\n".join(f"- {r['summary']}" for r in reversed(recent) if r['summary'])
            parts.append(recap)
            token_est += len(recap) // 2

        # 3. 出场角色——全部角色（简化，不再依赖 parent_id 树结构）
        characters = self.conn.execute(
            "SELECT name, role, traits FROM characters WHERE novel_id=?",
            (self.novel_id,)
        ).fetchall()

        if characters:
            char_text = "出场角色(请严格保持设定):\n"
            for c in characters:
                char_text += f"- {c['name']}({c['role']}): {c['traits']}\n"
            parts.append(char_text)
            token_est += len(char_text) // 2

        # 4. 活跃伏笔——open 状态的 (~300 tokens)
        threads = self.conn.execute(
            "SELECT description, tags, priority FROM plot_threads WHERE novel_id=? AND status='open' ORDER BY priority DESC LIMIT 5",
            (self.novel_id,)
        ).fetchall()
        if threads:
            thread_text = "待推进的剧情线(请在写作中考虑):\n"
            for t in threads:
                thread_text += f"- [{t['tags'] or '主线'}] {t['description']}\n"
            parts.append(thread_text)
            token_est += len(thread_text) // 2

        # 5. 世界观规则——当前章节标签相关的 (~200 tokens)
        tags = node.get("summary", "")
        rules = self.conn.execute(
            "SELECT key, value FROM world_rules WHERE novel_id=? ORDER BY id DESC LIMIT 8",
            (self.novel_id,)
        ).fetchall()
        if rules:
            rule_text = "世界观约束:\n"
            for r in rules:
                rule_text += f"- {r['key']}: {r['value']}\n"
            parts.append(rule_text)
            token_est += len(rule_text) // 2

        context_text = "\n\n".join(parts)

        # 记录上下文日志
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO context_logs (novel_id, section_id, context_json, token_estimate, created_at) VALUES (?,?,?,?,?)",
            (self.novel_id, node_id, json.dumps({"parts": len(parts)}, ensure_ascii=False),
             token_est, now)
        )
        self.conn.commit()

        return {
            "context_text": context_text,
            "characters": [dict(c) for c in characters],
            "threads": [dict(t) for t in threads],
            "rules": [dict(r) for r in rules],
            "recent_summaries": [r["summary"] for r in recent],
            "token_estimate": token_est,
        }

    # ================================================================
    # 状态查询
    # ================================================================

    def get_progress(self) -> dict:
        """获取总体进度（使用新平铺列）"""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM outline_nodes WHERE novel_id=? AND section_title != ''",
            (self.novel_id,)
        ).fetchone()[0]
        done = self.conn.execute(
            "SELECT COUNT(*) FROM outline_nodes WHERE novel_id=? AND section_title != '' AND status='done'",
            (self.novel_id,)
        ).fetchone()[0]
        words = self.conn.execute(
            "SELECT COALESCE(SUM(word_count),0) FROM sections WHERE novel_id=?",
            (self.novel_id,)
        ).fetchone()[0]
        chars = self.conn.execute(
            "SELECT COUNT(*) FROM characters WHERE novel_id=?", (self.novel_id,)
        ).fetchone()[0]
        threads_open = self.conn.execute(
            "SELECT COUNT(*) FROM plot_threads WHERE novel_id=? AND status='open'",
            (self.novel_id,)
        ).fetchone()[0]
        return {
            "total_sections": total, "done_sections": done,
            "total_words": words, "characters": chars,
            "open_threads": threads_open,
            "progress_pct": round(done / total * 100, 1) if total > 0 else 0,
        }

    def close(self):
        self.conn.close()

    # ================================================================
    # 审稿报告
    # ================================================================

    def save_review(self, content: str):
        """保存审稿报告"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO reviews (novel_id, content, created_at) VALUES (?,?,?)",
            (self.novel_id, content, now)
        )
        self.conn.commit()

    def get_latest_review(self) -> Optional[str]:
        """获取最新审稿报告"""
        row = self.conn.execute(
            "SELECT content FROM reviews WHERE novel_id=? ORDER BY id DESC LIMIT 1",
            (self.novel_id,)
        ).fetchone()
        return row["content"] if row else None
