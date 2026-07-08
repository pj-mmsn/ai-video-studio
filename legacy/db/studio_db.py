"""
数据协议 — 所有 Agent 共享的 DB 通信接口
============================================================
Agent 之间不直接调用，只通过这个数据库读写来协作。

流水线:
  Novelist 写 novels + sections → 
  Director 读 sections, 写 scenes + shots_prompts →
  Storyboard 读 shots_prompts, 写 shots →
  Videographer 读 shots, 写 clips

每个 Agent 有独立 CLI，独立配置，独立线程。
"""
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock

DB_DIR = Path(os.environ.get("AI_STUDIO_DB_DIR", "output/projects"))


class StudioDB:
    """所有 Agent 共享的数据库接口"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        db_path = DB_DIR / project_id / "studio.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = Lock()
        self._init()

    def _init(self):
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, title TEXT, genre TEXT, status TEXT,
                    created_at TEXT, updated_at TEXT
                );
                -- 小说家写入，导演读取
                CREATE TABLE IF NOT EXISTS sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT, volume INTEGER, chapter INTEGER, section INTEGER,
                    title TEXT, content TEXT, summary TEXT, word_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'draft', created_at TEXT
                );
                -- 导演写入，分镜师读取
                CREATE TABLE IF NOT EXISTS scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT, scene_number INTEGER,
                    description TEXT, visual_prompt TEXT, motion_prompt TEXT,
                    dialogue TEXT, camera TEXT, duration_sec INTEGER DEFAULT 5,
                    source_section_id INTEGER,
                    status TEXT DEFAULT 'pending', created_at TEXT
                );
                -- 分镜师写入，摄像师读取
                CREATE TABLE IF NOT EXISTS shots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT, scene_id INTEGER,
                    image_prompt TEXT, image_path TEXT, image_url TEXT,
                    motion_prompt TEXT, status TEXT DEFAULT 'pending', created_at TEXT
                );
                -- 摄像师写入
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT, shot_id INTEGER,
                    video_path TEXT, video_url TEXT,
                    prompt TEXT, duration_sec INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'pending', created_at TEXT
                );
                -- 故事圣经（所有Agent共维护）
                CREATE TABLE IF NOT EXISTS bible (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT, category TEXT, key TEXT, value TEXT,
                    source TEXT, created_at TEXT
                );
                -- 上下文日志
                CREATE TABLE IF NOT EXISTS context_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT, agent TEXT, section_id INTEGER,
                    context_json TEXT, token_estimate INTEGER, created_at TEXT
                );
            """)
            self.conn.commit()

    # ---- 工具方法 ----
    def _now(self): return datetime.now().isoformat()

    # ---- 项目 ----
    def create_project(self, title: str, genre: str = ""):
        with self._lock:
            self.conn.execute(
                "INSERT INTO projects VALUES (?,?,?,?,?,?)",
                (self.project_id, title, genre, "in_progress", self._now(), self._now()))
            self.conn.commit()

    def get_project(self):
        row = self.conn.execute("SELECT * FROM projects WHERE id=?", (self.project_id,)).fetchone()
        return dict(row) if row else None

    def update_status(self, status: str):
        with self._lock:
            self.conn.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?",
                            (status, self._now(), self.project_id))
            self.conn.commit()

    # ---- 小说家接口 ----
    def save_section(self, volume: int, chapter: int, section: int,
                     title: str, content: str, summary: str = "") -> int:
        with self._lock:
            c = self.conn.execute(
                """INSERT INTO sections (project_id,volume,chapter,section,title,content,summary,word_count,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (self.project_id, volume, chapter, section, title, content, summary,
                 len(content), 'done', self._now()))
            self.conn.commit()
            return c.lastrowid

    def get_sections(self, status: str = None) -> list[dict]:
        q = "SELECT * FROM sections WHERE project_id=? ORDER BY volume,chapter,section"
        rows = self.conn.execute(q, (self.project_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- 导演接口 ----
    def save_scene(self, scene_number: int, description: str, visual_prompt: str,
                   motion_prompt: str, dialogue: str, camera: str,
                   duration: int, source_section_id: int) -> int:
        with self._lock:
            c = self.conn.execute(
                """INSERT INTO scenes (project_id,scene_number,description,visual_prompt,
                motion_prompt,dialogue,camera,duration_sec,source_section_id,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (self.project_id, scene_number, description, visual_prompt,
                 motion_prompt, dialogue, camera, duration, source_section_id, 'pending', self._now()))
            self.conn.commit()
            return c.lastrowid

    def get_scenes(self, status: str = None) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scenes WHERE project_id=? ORDER BY scene_number",
            (self.project_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- 分镜师接口 ----
    def save_shot(self, scene_id: int, image_prompt: str,
                  image_path: str = "", image_url: str = "",
                  motion_prompt: str = "") -> int:
        with self._lock:
            c = self.conn.execute(
                """INSERT INTO shots (project_id,scene_id,image_prompt,image_path,image_url,motion_prompt,status,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (self.project_id, scene_id, image_prompt, image_path, image_url,
                 motion_prompt, 'done', self._now()))
            self.conn.commit()
            # 标记对应场景为 done
            self.conn.execute("UPDATE scenes SET status='done' WHERE id=?", (scene_id,))
            self.conn.commit()
            return c.lastrowid

    def get_pending_scenes(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scenes WHERE project_id=? AND status='pending' ORDER BY scene_number",
            (self.project_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- 摄像师接口 ----
    def save_clip(self, shot_id: int, video_path: str = "",
                  video_url: str = "", prompt: str = "", duration: int = 5) -> int:
        with self._lock:
            c = self.conn.execute(
                """INSERT INTO clips (project_id,shot_id,video_path,video_url,prompt,duration_sec,status,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (self.project_id, shot_id, video_path, video_url, prompt, duration, 'done', self._now()))
            self.conn.commit()
            return c.lastrowid

    def get_pending_shots(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM shots WHERE project_id=? AND status='pending' ORDER BY id",
            (self.project_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- 圣经（所有Agent共用）----
    def save_bible(self, category: str, key: str, value: str, source: str = ""):
        with self._lock:
            self.conn.execute(
                "INSERT INTO bible (project_id,category,key,value,source,created_at) VALUES (?,?,?,?,?,?)",
                (self.project_id, category, key, value, source, self._now()))
            self.conn.commit()

    def get_bible(self, category: str = None) -> list[dict]:
        q = "SELECT * FROM bible WHERE project_id=?"
        if category: q += " AND category=?"
        rows = self.conn.execute(q + " ORDER BY id", 
                                (self.project_id,) if not category else (self.project_id, category)).fetchall()
        return [dict(r) for r in rows]

    # ---- 进度 ----
    def progress(self) -> dict:
        sections = self.conn.execute("SELECT COUNT(*) FROM sections WHERE project_id=?", (self.project_id,)).fetchone()[0]
        scenes = self.conn.execute("SELECT COUNT(*) FROM scenes WHERE project_id=?", (self.project_id,)).fetchone()[0]
        shots = self.conn.execute("SELECT COUNT(*) FROM shots WHERE project_id=?", (self.project_id,)).fetchone()[0]
        clips = self.conn.execute("SELECT COUNT(*) FROM clips WHERE project_id=?", (self.project_id,)).fetchone()[0]
        words = self.conn.execute("SELECT COALESCE(SUM(word_count),0) FROM sections WHERE project_id=?", (self.project_id,)).fetchone()[0]
        return {"sections": sections, "scenes": scenes, "shots": shots, "clips": clips, "words": words}

    def close(self): self.conn.close()
