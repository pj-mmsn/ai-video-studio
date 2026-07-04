"""
Pipeline 编排器 — 串联 Agent + Reviewer 反馈循环
============================================================
改进版（知识库优化）：
    Director → Review → Storyboard → Review → Videographer → Review → 成片
    每个阶段产出后由 Reviewer 审查，不合格的退回重做（最多3次）。

设计模式：顺序管道 + 反馈循环（CrewAI 模式）
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
from src.agents.reviewer import ReviewerAgent, ReviewResult
from src.db.repository import ProjectRepository, StageStatus
from src.context.bible import StoryBible
from src.tools.composer import VideoComposer
from src.logging_config import info, warn, debug
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
    reviews: list[ReviewResult] = field(default_factory=list)
    composed_video_path: str = ""       # Stage 4 合成后的视频路径
    created_at: str = ""
    max_retries: int = 3

    def progress_report(self) -> str:
        stages = []
        stages.append("✅" if self.script else "⬜")
        stages.append("✅" if self.storyboard else "⬜")
        stages.append("✅" if self.clips else "⬜")
        review_str = f" | 审查{len(self.reviews)}次" if self.reviews else ""
        return f"剧本{stages[0]} → 分镜{stages[1]} → 视频{stages[2]}{review_str}"

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
        enable_reviewer: bool = True,
        reviewer_strictness: int = 6,
        project_id: str = None,          # 新增：项目 ID（支持断点续传）
    ):
        # 三个专业 Agent
        self.director = DirectorAgent(LLMClient(model=director_model))
        self.storyboard = StoryboardAgent(ImageGenClient(model=image_model))
        self.videographer = VideographerAgent(VideoGenClient(model=video_model))

        # 审查员
        self.reviewer = ReviewerAgent(
            llm_client=LLMClient() if enable_reviewer else None,
            strictness=reviewer_strictness,
        ) if enable_reviewer else None

        if use_mock:
            self.storyboard.use_mock = True
            self.videographer.use_mock = True

        # 数据库持久化层 + 故事圣经
        self.project_id = project_id or f"proj_{int(time.time())}"
        self.repo: ProjectRepository = None
        self.bible: StoryBible = None
        self._db_initialized = False

    # ================================================================
    # 全流程（含审查和重试）
    # ================================================================

    def produce(self, idea: str, style: str = "cinematic") -> Production:
        production = Production(
            title="", idea=idea, style=style,
            created_at=time.strftime("%Y-%m-%d %H:%M"),
        )

        # ---- 初始化数据库 ----
        self._init_db(idea, style)

        # ---- 断点续传检查 ----
        progress = self.repo.get_progress()
        if progress["can_resume"] and progress["last_stage"] != "done":
            print(f"\n🔄 检测到未完成项目，从 {progress['last_stage']} 阶段恢复...")
            print(f"   进度: 场景{progress['scenes_done']}/{progress['total_scenes']} "
                  f"| 分镜{progress['shots_done']} | 视频{progress['clips_done']}")

        # ---- 获取圣经上下文 ----
        bible_context = self.bible.get_context_text()

        print("=" * 60)
        print("🎬 AI 视频工作室 — 开始制作")
        print(f"   项目: {self.project_id}")
        print(f"   想法: {idea}  风格: {style}")
        if self.reviewer:
            print(f"   模式: 顺序管道 + 审查 + 数据库持久化")
        if bible_context:
            print(f"   📖 已加载故事圣经 ({self.bible.get_character_count()} 个角色)")
        print("=" * 60)

        # ---- Stage 1: 剧本（注入圣经上下文）----
        if progress["last_stage"] in ("new", "script"):
            # 把圣经注入到 Director
            if bible_context:
                self.director._bible_context = bible_context

            production.script = self._stage_with_review(
                "剧本",
                lambda: self.director.create_script(idea, style),
                lambda result: self.reviewer.review_script(result) if self.reviewer else None,
                production,
                max_retries=2,
            )
            production.title = production.script.title

            # 持久化场景 + 更新圣经
            self.repo.save_scenes(production.script.scenes)
            self.bible.update_from_script(production.script)
            self.repo.update_project(title=production.title, status="script_done")
            self._save_script(production.script)
        else:
            # 从数据库恢复
            scene_records = self.repo.get_scenes()
            from src.models import Scene as SceneModel
            production.script = Script(
                title=progress["project"].title,
                logline="",
                scenes=[SceneModel(
                    scene_id=r.scene_id, description=r.description,
                    visual_prompt=r.visual_prompt, motion_prompt=r.motion_prompt,
                    duration_sec=r.duration_sec, dialogue=r.dialogue, camera=r.camera,
                ) for r in scene_records],
            )
            production.title = progress["project"].title
            print(f"   🔄 从数据库恢复剧本: {len(scene_records)} 个场景")

        # ---- Stage 2: 分镜 ----
        if progress["last_stage"] in ("new", "script", "storyboard"):
            production.storyboard = self._stage_with_review(
                "分镜",
                lambda: self.storyboard.create_storyboard(production.script),
                lambda result: self.reviewer.review_storyboard(result) if self.reviewer else None,
                production,
                max_retries=2,
            )
            # 持久化分镜
            self.repo.save_shots(production.storyboard.shots)
            self.repo.update_project(status="storyboard_done")
            self._save_storyboard(production.storyboard)
        else:
            shot_records = self.repo.get_shots()
            from src.models import Shot as ShotModel
            production.storyboard = Storyboard(script_title=production.title)
            for r in shot_records:
                production.storyboard.shots.append(ShotModel(
                    scene_id=r.scene_id, image_prompt=r.image_prompt,
                    image_path=r.image_path or None, image_url=r.image_url or None,
                    motion_prompt=r.motion_prompt,
                ))
            print(f"   🔄 从数据库恢复分镜: {len(shot_records)} 个镜头")

        # ---- Stage 3: 视频 ----
        production.clips = self.videographer.produce(production.storyboard)
        self.repo.save_clips(production.clips)
        if self.reviewer:
            review = self.reviewer.review_clips(production.clips, production.storyboard)
            production.reviews.append(review)
            self.repo.save_review(review)

        self.repo.update_project(status="done", current_stage=len(production.clips))
        self._save_production(production)

        # ---- Stage 4: 视频合成（图片 → MP4）----
        try:
            composer = VideoComposer()
            video_path = composer.compose(production.storyboard, add_subtitles=True)
            if video_path:
                production.composed_video_path = video_path
                info(f"🎬 最终视频: {video_path}")
        except Exception as e:
            warn(f"视频合成跳过: {e}")

        # 打印审查总结
        bible_text = self.bible.get_context_text()
        if bible_text:
            info(f"\n📖 故事圣经 ({self.bible.get_character_count()} 个角色, 跨场景一致)")

        info(f"\n🎉 制作完成！")
        info(f"   项目: {self.project_id}")
        info(f"   数据库: {self.repo.db_path}")
        info(f"   {production.progress_report()}")
        if self.reviewer:
            info(f"   {self.reviewer.summary()}")
        info(f"   产出目录: {config.output_dir}")

        self.repo.close()
        return production

    def close(self):
        """关闭数据库连接"""
        if self.repo:
            self.repo.close()

    def _init_db(self, idea: str, style: str):
        """初始化数据库连接和故事圣经"""
        if self._db_initialized:
            return
        self.repo = ProjectRepository(self.project_id)
        self.bible = StoryBible(self.repo, LLMClient())
        progress = self.repo.get_progress()
        if not progress["can_resume"]:
            self.repo.create_project(idea, style)
        self._db_initialized = True

    # ================================================================
    # 带审查和重试的阶段执行器
    # ================================================================

    def _stage_with_review(self, stage_name, producer, review_fn, production, max_retries=2):
        """执行一个阶段，审查不合格则重试"""
        for attempt in range(max_retries + 1):
            result = producer()

            if not self.reviewer:
                return result

            review = review_fn(result) if callable(review_fn) else None
            if review:
                production.reviews.append(review)
                if review.passed:
                    return result
                if attempt < max_retries:
                    print(f"   🔄 {stage_name}审查未通过（第{attempt+1}次），重试中...")
                    if review.suggestions:
                        print(f"      建议: {review.suggestions[0][:80]}")
                else:
                    print(f"   ⚠️  {stage_name}重试{max_retries}次仍未通过审查，使用当前版本")

        return result

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
