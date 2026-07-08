"""
Stage 2: Storyboard Agent — 分镜师
============================================================
把剧本的每个场景转化为视觉分镜图。

输入: Script（场景列表，每个有 visual_prompt）
输出: Storyboard（每个场景对应一张图 + 动效提示词）

为什么用图像生成模型？
    文字描述→图像是跨模态转换，需要专门的生成模型。
    DALL-E 3 / Stable Diffusion / Midjourney 各有所长：
    - DALL-E 3: 理解自然语言最强，适合复杂描述
    - Stable Diffusion: 可控性最强（ControlNet/IP-Adapter）
    - Midjourney: 艺术性最强
"""
from __future__ import annotations

import time
from pathlib import Path

from src.models import ImageGenClient, Storyboard, Shot, Script
from src.logging_config import info


class StoryboardAgent:
    """分镜师 Agent

    为每个场景生成分镜图。
    支持真实 API（DALL-E/Stable Diffusion）和 Mock 模式。
    """

    def __init__(self, image_client: ImageGenClient = None):
        self.client = image_client or ImageGenClient()
        self.use_mock = not self.client.api_key or "mock" in self.client.api_key.lower()

    def create_storyboard(self, script: Script) -> Storyboard:
        """为剧本创建分镜

        Args:
            script: Director 产出的剧本

        Returns:
            Storyboard: 包含所有镜头图片的分镜板
        """
        storyboard = Storyboard(script_title=script.title)
        output_base = Path("output") / "storyboard" / script.title.replace(" ", "_")

        print(f"\n🎨 [Storyboard] 正在生成分镜图...")
        print(f"   剧本:《{script.title}》 {len(script.scenes)} 个场景")
        print(f"   模式: {'Mock 占位' if self.use_mock else f'真实 API ({self.client.name})'}")

        for scene in script.scenes:
            shot = self._create_shot(scene, output_base)
            storyboard.shots.append(shot)

        print(f"   ✅ 分镜完成: {len(storyboard.shots)} 个镜头")
        return storyboard

    def _create_shot(self, scene, output_base: Path) -> Shot:
        """为一个场景创建分镜镜头"""
        print(f"   🎞️  场景{scene.scene_id}: {scene.description[:40]}...")

        # 组合完整 prompt
        full_prompt = scene.visual_prompt
        if scene.camera:
            full_prompt += f", {scene.camera} shot"

        shot = Shot(
            scene_id=scene.scene_id,
            image_prompt=full_prompt,
            motion_prompt=scene.motion_prompt,
        )

        if self.use_mock:
            # Mock 模式：生成占位图
            path = str(output_base / f"scene_{scene.scene_id:02d}.png")
            shot.image_path = self.client.generate_mock(full_prompt, path)
            shot.image_url = None
        else:
            # 真实 API 模式
            try:
                url = self.client.generate(full_prompt)
                shot.image_url = url
                shot.image_path = None
                time.sleep(0.5)  # API rate limit
            except Exception as e:
                print(f"      ⚠️  生成失败: {e}")
                # fallback 到 mock
                path = str(output_base / f"scene_{scene.scene_id:02d}.png")
                shot.image_path = self.client.generate_mock(full_prompt, path)

        return shot
