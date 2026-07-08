"""
Storyboard Agent — 独立包
============================================================
只通过 StudioDB 通信：
  输入: 读 scenes 表（Director 写入的剧本场景）
  输出: 写 shots 表（Videographer 读取的分镜）

独立启动: python -m src.agents.storyboard_agent.cli --project my_novel
"""
from pathlib import Path
from app.config import load_config
from src.db.studio_db import StudioDB


class StoryboardAgent:
    """分镜师——读场景，生成分镜图"""

    def __init__(self, project_id: str, config: dict = None):
        self.project_id = project_id
        self.config = config or load_config()
        self.db = StudioDB(project_id)

    def generate(self, use_mock: bool = True) -> int:
        """为所有待处理场景生成分镜图"""
        scenes = self.db.get_pending_scenes()
        if not scenes:
            # 全部场景
            scenes = self.db.get_scenes()
            if not scenes:
                print("📭 没有场景，请先运行 Director")
                return 0

        total = 0
        for sc in scenes:
            print(f"🎨 分镜: 场景{sc['scene_number']}")

            if use_mock:
                # Mock: Pillow 占位图
                self._mock_shot(sc)
            else:
                self._real_shot(sc)

            total += 1

        return total

    def _mock_shot(self, scene: dict):
        """生成占位分镜图"""
        from PIL import Image, ImageDraw
        import textwrap

        out_dir = Path(f"output/projects/{self.project_id}/storyboard")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"scene_{scene['scene_number']:03d}.png"

        img = Image.new("RGB", (1024, 576), (20, 20, 40))
        d = ImageDraw.Draw(img)
        d.text((20, 20), f"Scene {scene['scene_number']}", fill=(200, 200, 220))
        wrapped = textwrap.wrap(scene.get("visual_prompt", "")[:200], width=60)
        for i, line in enumerate(wrapped[:8]):
            d.text((20, 60 + i * 25), line, fill=(150, 150, 180))
        img.save(str(path))

        self.db.save_shot(
            scene_id=scene["id"],
            image_prompt=scene["visual_prompt"],
            image_path=str(path),
            motion_prompt=scene.get("motion_prompt", ""),
        )
        print(f"   ✅ {path.name}")

    def _real_shot(self, scene: dict):
        """真实 API 生成（DALL-E 等）"""
        # TODO: 接入图像生成 API
        self._mock_shot(scene)

    def close(self): self.db.close()
