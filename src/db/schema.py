"""
数据库模型 — SQLite 持久化层
============================================================
设计理念：
    一个 Project（项目）包含多个 Scene（场景），
    每个 Scene 分阶段生成 Script → Shot → Clip → Review。
    每个阶段的状态、产出、错误都持久化，支持：
    1. 断点续传——崩溃后从上次中断处继续
    2. 增量修改——改一个场景不用重跑全部
    3. 上下文追踪——每个场景知道之前发生了什么

表结构：
    projects       — 项目元数据
    scenes         — 场景列表（剧本拆出来的）
    shots          — 分镜（每个场景的视觉输出）
    clips          — 视频片段
    reviews        — 审查记录
    story_bible    — 故事圣经（角色/场景一致性上下文）
"""
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

DB_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) / "output"


def get_db_path(project_id: str) -> Path:
    """每个项目一个独立的 SQLite 数据库"""
    db_dir = DB_DIR / "projects" / project_id
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "project.db"


# ================================================================
# 状态枚举
# ================================================================

class StageStatus:
    PENDING = "pending"         # 未开始
    IN_PROGRESS = "in_progress" # 进行中
    DONE = "done"               # 已完成
    REVIEWING = "reviewing"    # 审查中
    FAILED = "failed"          # 失败
    SKIPPED = "skipped"        # 跳过


# ================================================================
# 数据模型（和 Python dataclass 一一对应，便于序列化）
# ================================================================

@dataclass
class ProjectRecord:
    """项目记录"""
    project_id: str
    title: str = ""
    idea: str = ""
    style: str = "cinematic"
    status: str = StageStatus.PENDING
    current_stage: int = 0          # 当前进行到第几个场景
    total_scenes: int = 0
    metadata_json: str = "{}"       # 扩展字段
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(**{k: row[k] for k in row.keys()}) if row else None


@dataclass
class SceneRecord:
    """场景记录"""
    scene_id: int
    project_id: str
    description: str = ""
    visual_prompt: str = ""
    motion_prompt: str = ""
    dialogue: str = ""
    camera: str = ""
    duration_sec: int = 5
    status: str = StageStatus.PENDING
    error_msg: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(**{k: row[k] for k in row.keys()}) if row else None


@dataclass
class ShotRecord:
    """分镜记录"""
    shot_id: int
    scene_id: int
    project_id: str
    image_prompt: str = ""
    image_path: str = ""
    image_url: str = ""
    motion_prompt: str = ""
    status: str = StageStatus.PENDING
    created_at: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(**{k: row[k] for k in row.keys()}) if row else None


@dataclass
class ClipRecord:
    """视频片段记录"""
    clip_id: int
    scene_id: int
    project_id: str
    video_path: str = ""
    video_url: str = ""
    prompt: str = ""
    duration_sec: int = 5
    status: str = StageStatus.PENDING
    created_at: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(**{k: row[k] for k in row.keys()}) if row else None


@dataclass
class ReviewRecord:
    """审查记录"""
    review_id: int
    project_id: str
    target_stage: str = ""       # "剧本" | "分镜" | "视频"
    target_id: int = 0           # scene_id 或 shot_id 或 clip_id
    passed: bool = False
    score: int = 0
    issues_json: str = "[]"
    suggestions_json: str = "[]"
    created_at: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(**{k: row[k] for k in row.keys()}) if row else None


@dataclass
class StoryBibleEntry:
    """故事圣经条目——维护跨场景一致性"""
    entry_id: int
    project_id: str
    category: str = ""           # character/location/prop/plot_point/style_rule
    key: str = ""                # 条目名（如 "主角名字"）
    value: str = ""              # 条目值（如 "小明"）
    source_scene: int = 0        # 首次出现在哪个场景
    updated_at: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(**{k: row[k] for k in row.keys()}) if row else None
