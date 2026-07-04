"""
Repository 层 — 数据库操作 + 断点续传
============================================================
每个项目独立 SQLite 文件，存储在 output/projects/<project_id>/project.db。

断点续传逻辑：
    1. produce() 开始时——检查项目是否存在，存在则从 last checkpoint 恢复
    2. 每个 Stage 完成后——自动保存 checkpoint
    3. produce() 失败后——下次调用自动恢复到最后一次成功的 Stage
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schema import (
    get_db_path, StageStatus,
    ProjectRecord, SceneRecord, ShotRecord, ClipRecord,
    ReviewRecord, StoryBibleEntry,
)


class ProjectRepository:
    """项目管理——CRUD + 断点续传"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.db_path = get_db_path(project_id)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    # ---------------------------------------------------------------
    # 建表
    # ---------------------------------------------------------------

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                idea TEXT DEFAULT '',
                style TEXT DEFAULT 'cinematic',
                status TEXT DEFAULT 'pending',
                current_stage INTEGER DEFAULT 0,
                total_scenes INTEGER DEFAULT 0,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS scenes (
                scene_id INTEGER,
                project_id TEXT,
                description TEXT DEFAULT '',
                visual_prompt TEXT DEFAULT '',
                motion_prompt TEXT DEFAULT '',
                dialogue TEXT DEFAULT '',
                camera TEXT DEFAULT '',
                duration_sec INTEGER DEFAULT 5,
                status TEXT DEFAULT 'pending',
                error_msg TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                PRIMARY KEY (scene_id, project_id)
            );

            CREATE TABLE IF NOT EXISTS shots (
                shot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER NOT NULL,
                project_id TEXT NOT NULL,
                image_prompt TEXT DEFAULT '',
                image_path TEXT DEFAULT '',
                image_url TEXT DEFAULT '',
                motion_prompt TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS clips (
                clip_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER NOT NULL,
                project_id TEXT NOT NULL,
                video_path TEXT DEFAULT '',
                video_url TEXT DEFAULT '',
                prompt TEXT DEFAULT '',
                duration_sec INTEGER DEFAULT 5,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                target_stage TEXT DEFAULT '',
                target_id INTEGER DEFAULT 0,
                passed INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0,
                issues_json TEXT DEFAULT '[]',
                suggestions_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS story_bible (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                category TEXT DEFAULT '',
                key TEXT DEFAULT '',
                value TEXT DEFAULT '',
                source_scene INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT ''
            );
        """)
        self.conn.commit()

    # ---------------------------------------------------------------
    # 项目 CRUD
    # ---------------------------------------------------------------

    def create_project(self, idea: str, style: str, title: str = "") -> ProjectRecord:
        now = datetime.now().isoformat()
        rec = ProjectRecord(
            project_id=self.project_id,
            title=title or f"未命名项目_{self.project_id[:8]}",
            idea=idea,
            style=style,
            status=StageStatus.IN_PROGRESS,
            created_at=now,
            updated_at=now,
        )
        self.conn.execute(
            """INSERT OR REPLACE INTO projects
            (project_id, title, idea, style, status, current_stage, total_scenes,
             metadata_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (rec.project_id, rec.title, rec.idea, rec.style, rec.status,
             rec.current_stage, rec.total_scenes, rec.metadata_json,
             rec.created_at, rec.updated_at)
        )
        self.conn.commit()
        return rec

    def get_project(self) -> Optional[ProjectRecord]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE project_id=?", (self.project_id,)
        ).fetchone()
        return ProjectRecord.from_row(row) if row else None

    def update_project(self, **kwargs):
        kwargs["updated_at"] = datetime.now().isoformat()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [self.project_id]
        self.conn.execute(
            f"UPDATE projects SET {sets} WHERE project_id=?",
            vals
        )
        self.conn.commit()

    # ---------------------------------------------------------------
    # 场景 CRUD
    # ---------------------------------------------------------------

    def save_scenes(self, scenes: list) -> None:
        """批量保存场景（首次从剧本导入）"""
        now = datetime.now().isoformat()
        for s in scenes:
            self.conn.execute(
                """INSERT OR REPLACE INTO scenes
                (scene_id, project_id, description, visual_prompt, motion_prompt,
                 dialogue, camera, duration_sec, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (s.scene_id, self.project_id, s.description, s.visual_prompt,
                 s.motion_prompt, s.dialogue, s.camera, s.duration_sec,
                 StageStatus.PENDING, now, now)
            )
        self.conn.commit()
        self.update_project(total_scenes=len(scenes))

    def get_scenes(self, status: str = None) -> list[SceneRecord]:
        """获取场景列表，可按状态过滤"""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM scenes WHERE project_id=? AND status=? ORDER BY scene_id",
                (self.project_id, status)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM scenes WHERE project_id=? ORDER BY scene_id",
                (self.project_id,)
            ).fetchall()
        return [SceneRecord.from_row(r) for r in rows]

    def update_scene(self, scene_id: int, **kwargs):
        kwargs["updated_at"] = datetime.now().isoformat()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [scene_id, self.project_id]
        self.conn.execute(
            f"UPDATE scenes SET {sets} WHERE scene_id=? AND project_id=?", vals
        )
        self.conn.commit()

    # ---------------------------------------------------------------
    # 分镜 CRUD
    # ---------------------------------------------------------------

    def save_shots(self, shots: list) -> None:
        now = datetime.now().isoformat()
        for s in shots:
            self.conn.execute(
                """INSERT INTO shots
                (scene_id, project_id, image_prompt, image_path, image_url,
                 motion_prompt, status, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (s.scene_id, self.project_id, s.image_prompt, s.image_path or "",
                 s.image_url or "", s.motion_prompt, StageStatus.DONE, now)
            )
            self.update_scene(s.scene_id, status=StageStatus.DONE)
        self.conn.commit()

    def get_shots(self) -> list[ShotRecord]:
        rows = self.conn.execute(
            "SELECT * FROM shots WHERE project_id=? ORDER BY scene_id",
            (self.project_id,)
        ).fetchall()
        return [ShotRecord.from_row(r) for r in rows]

    # ---------------------------------------------------------------
    # 视频片段 CRUD
    # ---------------------------------------------------------------

    def save_clips(self, clips: list) -> None:
        now = datetime.now().isoformat()
        for c in clips:
            self.conn.execute(
                """INSERT INTO clips
                (scene_id, project_id, video_path, video_url, prompt,
                 duration_sec, status, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (c.scene_id, self.project_id, c.video_path or "",
                 c.video_url or "", c.prompt, c.duration_sec,
                 StageStatus.DONE, now)
            )
        self.conn.commit()

    def get_clips(self) -> list[ClipRecord]:
        rows = self.conn.execute(
            "SELECT * FROM clips WHERE project_id=? ORDER BY scene_id",
            (self.project_id,)
        ).fetchall()
        return [ClipRecord.from_row(r) for r in rows]

    # ---------------------------------------------------------------
    # 审查 CRUD
    # ---------------------------------------------------------------

    def save_review(self, review) -> None:
        now = datetime.now().isoformat()
        target_id = getattr(review, 'target_id', 0) or 0
        self.conn.execute(
            """INSERT INTO reviews
            (project_id, target_stage, target_id, passed, score,
             issues_json, suggestions_json, created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (self.project_id, review.target_stage or "", target_id,
             1 if review.passed else 0, review.score or 0,
             json.dumps(getattr(review, 'issues', []) or [], ensure_ascii=False),
             json.dumps(getattr(review, 'suggestions', []) or [], ensure_ascii=False),
             now)
        )
        self.conn.commit()

    def get_reviews(self) -> list[ReviewRecord]:
        rows = self.conn.execute(
            "SELECT * FROM reviews WHERE project_id=? ORDER BY review_id",
            (self.project_id,)
        ).fetchall()
        return [ReviewRecord.from_row(r) for r in rows]

    # ---------------------------------------------------------------
    # 故事圣经 (Story Bible) — 跨场景一致性
    # ---------------------------------------------------------------

    def save_bible_entry(self, category: str, key: str, value: str, source_scene: int = 0):
        """保存一条故事圣经条目"""
        now = datetime.now().isoformat()
        # UPSERT: 如果同 category+key 已存在，更新之
        existing = self.conn.execute(
            "SELECT entry_id FROM story_bible WHERE project_id=? AND category=? AND key=?",
            (self.project_id, category, key)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE story_bible SET value=?, source_scene=?, updated_at=? WHERE entry_id=?",
                (value, source_scene, now, existing["entry_id"])
            )
        else:
            self.conn.execute(
                """INSERT INTO story_bible
                (project_id, category, key, value, source_scene, updated_at)
                VALUES (?,?,?,?,?,?)""",
                (self.project_id, category, key, value, source_scene, now)
            )
        self.conn.commit()

    def get_bible_text(self) -> str:
        """导出故事圣经为文本（注入到 Director 的 system prompt 中）

        格式：
        ## 故事圣经（请严格遵循以下设定）
        ### 角色
        - 主角: 小明（一个12岁的男孩，戴眼镜）
        - 配角: 小黑（一只会说话的猫）

        ### 场景设定
        - 主要场景: 霓虹灯下的东京街头
        - 世界观: 近未来赛博朋克

        ### 剧情要点
        - 核心冲突: 主角在寻找失踪的父亲
        - 关键道具: 一把发光的钥匙
        """
        entries = self.conn.execute(
            "SELECT * FROM story_bible WHERE project_id=? ORDER BY category, key",
            (self.project_id,)
        ).fetchall()

        if not entries:
            return ""

        by_category = {}
        for e in entries:
            cat = e["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((e["key"], e["value"], e["source_scene"]))

        category_names = {
            "character": "角色",
            "location": "场景设定",
            "prop": "关键道具",
            "plot_point": "剧情要点",
            "style_rule": "视觉风格规则",
            "world_building": "世界观",
        }

        lines = ["## 故事圣经（请严格遵循以下设定，保持前后一致）"]
        for cat, items in by_category.items():
            label = category_names.get(cat, cat)
            lines.append(f"\n### {label}")
            for key, value, scene in items:
                lines.append(f"- {key}: {value}（首次出现: 场景{scene}）")

        return "\n".join(lines)

    # ---------------------------------------------------------------
    # 断点续传
    # ---------------------------------------------------------------

    def get_progress(self) -> dict:
        """获取项目当前进度——用于断点续传

        Returns:
            {
                "project": ProjectRecord,
                "total_scenes": int,
                "scenes_done": int,
                "shots_done": int,
                "clips_done": int,
                "reviews_count": int,
                "last_stage": str,       # "script" | "storyboard" | "video" | "done"
                "can_resume": bool
            }
        """
        project = self.get_project()
        if not project:
            return {"can_resume": False}

        scenes_done = self.conn.execute(
            "SELECT COUNT(*) FROM scenes WHERE project_id=? AND status='done'",
            (self.project_id,)
        ).fetchone()[0]

        shots_done = self.conn.execute(
            "SELECT COUNT(*) FROM shots WHERE project_id=?",
            (self.project_id,)
        ).fetchone()[0]

        clips_done = self.conn.execute(
            "SELECT COUNT(*) FROM clips WHERE project_id=?",
            (self.project_id,)
        ).fetchone()[0]

        reviews = self.get_reviews()

        # 判断当前进度
        if clips_done > 0:
            last_stage = "done"
        elif shots_done > 0:
            last_stage = "video"
        elif scenes_done > 0:
            last_stage = "storyboard"
        elif project.total_scenes > 0:
            last_stage = "script"
        else:
            last_stage = "new"

        return {
            "project": project,
            "total_scenes": project.total_scenes,
            "scenes_done": scenes_done,
            "shots_done": shots_done,
            "clips_done": clips_done,
            "reviews_count": len(reviews),
            "last_stage": last_stage,
            "can_resume": last_stage != "new",
        }

    def close(self):
        self.conn.close()
