"""
多模型视频工作室 — 全局配置
============================================================
三个模型各司其职：
    Stage 1 - Director: 推理模型 → 剧本
    Stage 2 - Storyboard: 图像模型 → 分镜图
    Stage 3 - Videographer: 视频模型 → 成片
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class DirectorConfig:
    """Stage 1: 剧本导演 — 推理/创意模型"""
    api_key: str = field(default_factory=lambda: os.getenv("DIRECTOR_API_KEY", os.getenv("LLM_API_KEY", "")))
    base_url: str = field(default_factory=lambda: os.getenv("DIRECTOR_BASE_URL", os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")))
    model: str = field(default_factory=lambda: os.getenv("DIRECTOR_MODEL", "gpt-4o"))
    temperature: float = 0.8  # 创意任务用较高温度


@dataclass
class StoryboardConfig:
    """Stage 2: 分镜师 — 图像生成模型"""
    api_key: str = field(default_factory=lambda: os.getenv("IMAGE_API_KEY", os.getenv("LLM_API_KEY", "")))
    base_url: str = field(default_factory=lambda: os.getenv("IMAGE_BASE_URL", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: os.getenv("IMAGE_MODEL", "dall-e-3"))
    image_size: str = "1024x1024"
    images_per_scene: int = 1


@dataclass
class VideographerConfig:
    """Stage 3: 摄像师 — 视频生成模型"""
    api_key: str = field(default_factory=lambda: os.getenv("VIDEO_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("VIDEO_BASE_URL", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: os.getenv("VIDEO_MODEL", "sora"))
    duration: int = 5  # 每秒
    resolution: str = "1080p"


@dataclass
class Config:
    director: DirectorConfig = field(default_factory=DirectorConfig)
    storyboard: StoryboardConfig = field(default_factory=StoryboardConfig)
    videographer: VideographerConfig = field(default_factory=VideographerConfig)
    output_dir: Path = field(default_factory=lambda: Path("output"))


config = Config()
