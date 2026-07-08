"""
小说写作 — 业务逻辑层
=====================
从 API 层分离出来的核心业务：上下文构建、内容保存、进度更新等。
"""
import datetime
from app.db.repository import NovelRepository
from app.utils import clean_output, count_words


class NovelService:
    """小说写作业务逻辑"""

    def __init__(self, novel_id: str):
        self.novel_id = novel_id
        self.repo = NovelRepository(novel_id, "output/novels")

    def get_context(self, node_id: int) -> dict:
        """获取写作上下文"""
        return self.repo.get_writing_context(node_id) if hasattr(self.repo, 'get_writing_context') else {"context_text": ""}

    def get_node(self, node_id: int):
        """获取大纲节点"""
        return self.repo.conn.execute(
            "SELECT volume_title, chapter_title, section_order, section_title, summary, status "
            "FROM outline_nodes WHERE id=?", (node_id,)
        ).fetchone()

    def get_existing_content(self, node_id: int) -> str:
        """获取已写内容"""
        row = self.repo.conn.execute(
            "SELECT content FROM sections WHERE outline_node_id=? ORDER BY version DESC LIMIT 1",
            (node_id,)
        ).fetchone()
        return row[0] if row else ""

    def save_section(self, node_id: int, raw_text: str):
        """保存写作结果"""
        body = clean_output(raw_text)
        summary = ""
        if "【本节摘要】" in body:
            parts = body.split("【本节摘要】")
            body = parts[0].strip()
            summary = parts[1].strip() if len(parts) > 1 else ""

        wc = count_words(body)
        now = datetime.datetime.now().isoformat()
        self.repo.conn.execute(
            "INSERT INTO sections (novel_id, outline_node_id, content, word_count, summary, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (self.novel_id, node_id, body, wc, summary, now, now))
        self.repo.conn.execute("UPDATE outline_nodes SET status='done' WHERE id=?", (node_id,))
        self.repo.conn.execute(
            "UPDATE novels SET total_words=(SELECT COALESCE(SUM(word_count),0) FROM sections WHERE novel_id=?), "
            "updated_at=? WHERE id=?",
            (self.novel_id, now, self.novel_id))
        self.repo.conn.commit()

    def save_idea(self, parsed: dict):
        """保存构思结果"""
        now = datetime.datetime.now().isoformat()
        self.repo.conn.execute(
            "UPDATE novels SET title=?, genre=?, premise=?, updated_at=? WHERE id=?",
            (parsed.get("title", ""), parsed.get("genre", ""), parsed.get("premise", ""), now, self.novel_id))
        self.repo.conn.execute(
            "INSERT OR REPLACE INTO story_bible (project_id, category, key, value) VALUES (?,?,?,?)",
            (self.novel_id, "world_building", "main", parsed.get("world_building", "")))
        self.repo.conn.execute("DELETE FROM characters WHERE novel_id=?", (self.novel_id,))
        for c in parsed.get("characters", []):
            self.repo.conn.execute(
                "INSERT INTO characters (novel_id, name, role, traits, desire, fear) VALUES (?,?,?,?,?,?)",
                (self.novel_id, c.get("name", ""), c.get("role", ""),
                 c.get("traits", ""), c.get("desire", ""), c.get("fear", "")))
        self.repo.conn.commit()

    def save_outline(self, parsed: dict):
        """保存大纲"""
        self.repo.conn.execute("DELETE FROM outline_nodes WHERE novel_id=?", (self.novel_id,))
        sort = 0
        for vi, vol in enumerate(parsed.get("volumes", [])):
            vt = vol.get("title", f"第{vi+1}卷")
            self.repo.conn.execute(
                "INSERT INTO outline_nodes (novel_id, volume_title, sort_order) VALUES (?,?,?)",
                (self.novel_id, vt, sort)); sort += 1
            for ci, ch in enumerate(vol.get("chapters", [])):
                ct = ch.get("title", f"第{ci+1}章")
                self.repo.conn.execute(
                    "INSERT INTO outline_nodes (novel_id, volume_title, chapter_title, summary, sort_order) VALUES (?,?,?,?,?)",
                    (self.novel_id, vt, ct, ch.get("summary", ""), sort)); sort += 1
                for si, sec in enumerate(ch.get("sections", [])):
                    self.repo.conn.execute(
                        "INSERT INTO outline_nodes (novel_id, volume_title, chapter_title, section_order, section_title, summary, sort_order) VALUES (?,?,?,?,?,?,?)",
                        (self.novel_id, vt, ct, si+1, sec.get("title", ""), sec.get("summary", ""), sort)); sort += 1
        self.repo.conn.commit()

    def close(self):
        self.repo.close()
