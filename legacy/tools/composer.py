"""
视频合成器 — 把分镜图拼成可播放的视频
============================================================
依赖: pip install moviepy pillow

功能:
    - 分镜图 → MP4（每张图按 duration_sec 显示）
    - 叠加旁白音频（edge-tts 生成）
    - 硬字幕渲染（dialogue 字段）
"""
from __future__ import annotations

import os
import asyncio
import tempfile
from pathlib import Path

from src.logging_config import info, warn


class VideoComposer:
    """视频合成器"""

    def __init__(self, fps: int = 24):
        self.fps = fps

    def compose(
        self,
        storyboard,       # Storyboard
        output_path: str = None,
        add_subtitles: bool = True,
        add_narration: bool = False,
    ) -> str:
        """将分镜合成为视频

        Args:
            storyboard: 分镜板（含 shots 和 script 信息）
            output_path: 输出路径，默认 output/video/<title>.mp4
            add_subtitles: 是否添加硬字幕
            add_narration: 是否合成旁白（需要 edge-tts）

        Returns:
            输出视频路径
        """
        output = output_path or f"output/video/{storyboard.script_title.replace(' ', '_')}.mp4"
        output = str(Path(output))
        Path(output).parent.mkdir(parents=True, exist_ok=True)

        try:
            from PIL import Image, ImageDraw, ImageFont
            from moviepy import ImageClip, concatenate_videoclips, CompositeVideoClip, TextClip
            from moviepy.video.fx import FadeIn, FadeOut

            clips = []
            for i, shot in enumerate(storyboard.shots):
                img_path = shot.image_path
                if not img_path or not Path(img_path).exists():
                    # 生成占位图
                    img_path = self._make_placeholder(shot, i)

                duration = getattr(shot, 'duration_sec', 5) or 5

                clip = ImageClip(img_path, duration=duration)

                # 加淡入淡出
                if i == 0:
                    clip = clip.with_effects([FadeIn(0.5)])
                if i == len(storyboard.shots) - 1:
                    clip = clip.with_effects([FadeOut(0.5)])

                # 硬字幕
                if add_subtitles and hasattr(shot, 'dialogue') and shot.dialogue:
                    subtitle = TextClip(
                        text=shot.dialogue,
                        font_size=32,
                        color='white',
                        stroke_color='black',
                        stroke_width=2,
                        method='caption',
                        size=(clip.w - 100, None),
                    ).with_position(('center', clip.h - 100)).with_duration(duration)
                    clip = CompositeVideoClip([clip, subtitle])

                clips.append(clip)

            final = concatenate_videoclips(clips, method="compose")
            final.write_videofile(output, fps=self.fps, logger=None)
            info(f"🎬 视频已合成: {output} ({len(clips)} 个片段, {final.duration:.1f}s)")

            return output

        except ImportError as e:
            warn(f"视频合成库不可用: {e}")
            warn("  安装: pip install moviepy pillow")
            # 降级：生成图片序列文件夹
            img_dir = str(Path(output).with_suffix(""))
            Path(img_dir).mkdir(parents=True, exist_ok=True)
            for i, shot in enumerate(storyboard.shots):
                img_path = shot.image_path
                if img_path and Path(img_path).exists():
                    import shutil
                    shutil.copy(img_path, f"{img_dir}/frame_{i:04d}.png")
            info(f"📁 降级模式: 图片已保存至 {img_dir}/ (需手动合成)")
            return ""

    def _make_placeholder(self, shot, index: int) -> str:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (1024, 1024), color=(20, 20, 40))
        draw = ImageDraw.Draw(img)
        draw.text((50, 500), f"Scene {index+1}", fill=(200, 200, 220))
        path = f"output/video/temp_shot_{index}.png"
        img.save(path)
        return path


class Narrator:
    """旁白生成器"""

    async def generate_speech(self, text: str, output_path: str) -> str:
        """用 edge-tts 生成语音文件"""
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
            await communicate.save(output_path)
            return output_path
        except ImportError:
            warn("edge-tts 未安装，跳过旁白: pip install edge-tts")
            return ""
        except Exception as e:
            warn(f"旁白生成失败: {e}")
            return ""

    async def generate_all_dialogues(self, storyboard) -> list[str]:
        """为所有场景生成旁白音频"""
        paths = []
        for i, shot in enumerate(storyboard.shots):
            dialogue = getattr(shot, 'dialogue', '')
            if dialogue:
                path = f"output/video/narration_{i:02d}.mp3"
                result = await self.generate_speech(dialogue, path)
                if result:
                    paths.append(result)
        return paths
