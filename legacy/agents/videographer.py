"""
Stage 3: Videographer Agent — 摄像师
============================================================
把分镜图转化为视频片段。

输入: Storyboard（每个 shot 有图片 + motion_prompt）
输出: 视频片段列表

真实 API 选项：
    - RunwayML Gen-3: 图生视频，质量最高
    - Pika Labs: 性价比高，社区活跃
    - Kling (可灵): 国产，中文理解好
    - ComfyUI + AnimateDiff: 本地免费方案
"""
from __future__ import annotations

from pathlib import Path

from src.models import VideoGenClient, VideoClip, Storyboard, Shot
from src.logging_config import info


class VideographerAgent:
    """摄像师 Agent

    把分镜图转为动态视频。
    当前支持 Mock 模式（生成占位帧），真实 API 接入见文档。
    """

    def __init__(self, video_client: VideoGenClient = None):
        self.client = video_client or VideoGenClient()
        self.use_mock = not self.client.api_key or "mock" in self.client.api_key.lower()

    def produce(self, storyboard: Storyboard) -> list[VideoClip]:
        """将分镜制作为视频片段

        Args:
            storyboard: Storyboard Agent 产出的分镜板

        Returns:
            视频片段列表（按场景顺序）
        """
        clips = []
        output_base = Path("output") / "video" / storyboard.script_title.replace(" ", "_")

        print(f"\n🎥 [Videographer] 正在生成视频...")
        print(f"   分镜数: {len(storyboard.shots)} 个镜头")
        print(f"   模式: {'Mock 占位' if self.use_mock else f'真实 API ({self.client.name})'}")

        for shot in storyboard.shots:
            clip = self._create_clip(shot, output_base)
            clips.append(clip)

        print(f"   ✅ 视频生成完成: {len(clips)} 个片段")
        return clips

    def _create_clip(self, shot: Shot, output_base: Path) -> VideoClip:
        """从一个 分镜 生成视频片段"""
        print(f"   🎬 场景{shot.scene_id}: {shot.motion_prompt[:50]}...")

        image_source = shot.image_path or shot.image_url or ""

        if self.use_mock:
            path = self.client._generate_mock(image_source, shot.motion_prompt)
            return VideoClip(
                scene_id=shot.scene_id,
                video_path=path,
                duration_sec=5,
                prompt=shot.motion_prompt,
            )
        else:
            try:
                path = self.client.generate(
                    image_source, shot.motion_prompt,
                    duration=5,
                )
                return VideoClip(
                    scene_id=shot.scene_id,
                    video_path=path,
                    duration_sec=5,
                    prompt=shot.motion_prompt,
                )
            except Exception as e:
                print(f"      ⚠️  生成失败: {e}")
                return VideoClip(
                    scene_id=shot.scene_id,
                    prompt=shot.motion_prompt,
                )
