"""
Pipeline 编排器 — 串联三个 Agent 的导演
============================================================
这是整个项目的核心——像电影制片人一样协调三个专业 Agent：
    Director → Storyboard → Videographer → 最终成片

设计模式：管道模式 (Pipeline Pattern)
    每个阶段的输出是下一个阶段的输入。
    和知识库中 Multi-Agent 的"顺序管道"模式一致。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.models import LLMClient, ImageGenClient, VideoGenClient
from src.models import Script, Storyboard, VideoClip
from src.agents.director import DirectorAgent
from src.agents.storyboard import StoryboardAgent
from src.agents.videographer import VideographerAgent
from config import config


@dataclass
class Production:
    """一部完整作品"""
    title: str
    idea: str
    style: str
    script: Script = None
    storyboard: Storyboard = None
    clips: list[VideoClip] = field(default_factory=list)
    created_at: str = ""

    def progress_report(self) -> str:
        stages = []
        stages.append("✅" if self.script else "⬜")
        stages.append("✅" if self.storyboard else "⬜")
        stages.append("✅" if self.clips else "⬜")
        return f"剧本{stages[0]} → 分镜{stages[1]} → 视频{stages[2]}"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "idea": self.idea,
            "style": self.style,
            "scenes": len(self.script.scenes) if self.script else 0,
            "shots": len(self.storyboard.shots) if self.storyboard else 0,
            "clips": len(self.clips),
            "progress": self.progress_report(),
        }


class VideoPipeline:
    """视频制作流水线——整个工作室的总指挥

    使用方式:
        pipeline = VideoPipeline()
        production = await pipeline.produce("一只猫在太空站冒险", style="anime")
        print(production.progress_report())

    三段式流水线:
        Idea → [Director] → Script → [Storyboard] → Images → [Videographer] → Video
    """

    def __init__(
        self,
        director_model: str = None,
        image_model: str = None,
        video_model: str = None,
        use_mock: bool = False,
    ):
        """
        Args:
            director_model: 剧本模型（如 gpt-4o / deepseek-chat）
            image_model: 图像模型（如 dall-e-3）
            video_model: 视频模型（如 runway-gen3）
            use_mock: 是否使用 Mock 模式（无 API Key 时测试用）
        """
        # 初始化三个 Agent
        self.director = DirectorAgent(LLMClient(model=director_model))
        self.storyboard = StoryboardAgent(ImageGenClient(model=image_model))
        self.videographer = VideographerAgent(VideoGenClient(model=video_model))

        if use_mock:
            # Mock 模式
            self.storyboard.use_mock = True
            self.videographer.use_mock = True

    # ================================================================
    # 全流程
    # ================================================================

    def produce(self, idea: str, style: str = "cinematic") -> Production:
        """完整制作流程：从想法到成片

        Args:
            idea: 创意想法（如"一只猫在太空站冒险"）
            style: 视觉风格（cinematic/anime/3d/watercolor/pixel-art）

        Returns:
            Production: 完整作品
        """
        production = Production(
            title="",
            idea=idea,
            style=style,
            created_at=time.strftime("%Y-%m-%d %H:%M"),
        )

        print("=" * 60)
        print("🎬 AI 视频工作室 — 开始制作")
        print(f"   想法: {idea}")
        print(f"   风格: {style}")
        print("=" * 60)

        # ---- Stage 1: 剧本 ----
        production.script = self.director.create_script(idea, style)
        production.title = production.script.title
        self._save_script(production.script)

        # ---- Stage 2: 分镜 ----
        production.storyboard = self.storyboard.create_storyboard(production.script)
        self._save_storyboard(production.storyboard)

        # ---- Stage 3: 视频 ----
        production.clips = self.videographer.produce(production.storyboard)
        self._save_production(production)

        print("\n" + "=" * 60)
        print("🎉 制作完成！")
        print(f"   {production.progress_report()}")
        print(f"   产出目录: {config.output_dir}")
        print("=" * 60)

        return production

    # ================================================================
    # 分步执行（方便调试和单步测试）
    # ================================================================

    def step1_script(self, idea: str, style: str = "cinematic") -> Script:
        """仅执行第一步：生成剧本"""
        return self.director.create_script(idea, style)

    def step2_storyboard(self, script: Script) -> Storyboard:
        """仅执行第二步：生成分镜"""
        return self.storyboard.create_storyboard(script)

    def step3_video(self, storyboard: Storyboard) -> list[VideoClip]:
        """仅执行第三步：生成视频"""
        return self.videographer.produce(storyboard)

    # ================================================================
    # 持久化
    # ================================================================

    def _save_script(self, script: Script):
        path = config.output_dir / "scripts" / f"{script.title}.json"
        path = Path(str(path).replace(" ", "_"))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "title": script.title,
            "logline": script.logline,
            "scenes": [
                {
                    "scene_id": s.scene_id,
                    "description": s.description,
                    "visual_prompt": s.visual_prompt,
                    "motion_prompt": s.motion_prompt,
                    "dialogue": s.dialogue,
                    "camera": s.camera,
                }
                for s in script.scenes
            ],
            "raw_text": script.raw_text[:500],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   💾 剧本已保存: {path}")

    def _save_storyboard(self, storyboard: Storyboard):
        path = config.output_dir / "storyboard" / f"{storyboard.script_title}_shots.json"
        path = Path(str(path).replace(" ", "_"))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "title": storyboard.script_title,
            "shots": [
                {
                    "scene_id": s.scene_id,
                    "prompt": s.image_prompt,
                    "image_path": s.image_path,
                    "motion_prompt": s.motion_prompt,
                }
                for s in storyboard.shots
            ],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_production(self, production: Production):
        path = config.output_dir / "productions.json"
        productions = []
        if path.exists():
            productions = json.loads(path.read_text(encoding="utf-8"))
        productions.append(production.to_dict())
        path.write_text(json.dumps(productions, ensure_ascii=False, indent=2), encoding="utf-8")
