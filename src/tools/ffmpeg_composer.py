"""
FFmpeg 增强合成器 — 生产级视频输出
============================================================
支持：转场特效 / 背景音乐 / 硬字幕 / 水印 / 多分辨率

前提：系统已安装 ffmpeg（PATH 中可用）
  Windows: choco install ffmpeg  或下载 ffmpeg.org
  Mac: brew install ffmpeg
  Linux: apt install ffmpeg
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from src.logging_config import info, warn


class FFmpegComposer:
    """基于 FFmpeg 的专业视频合成器"""

    def __init__(self, fps: int = 24):
        self.fps = fps

    def compose(
        self,
        image_dir: str,
        output_path: str,
        duration_per_image: int = 5,
        transition: str = "fade",
        music_path: str = None,
        subtitle_texts: list[str] = None,
        watermark_text: str = None,
        width: int = 1920,
        height: int = 1080,
    ) -> str:
        """将图片序列合成为带特效的视频

        Args:
            image_dir: 包含 scene_01.png, scene_02.png ... 的目录
            output_path: 输出 MP4 路径
            duration_per_image: 每张图显示秒数
            transition: 转场类型 (fade/slide/zoom/none)
            music_path: 背景音乐路径
            subtitle_texts: 字幕文本列表（和图片一一对应）
            watermark_text: 水印文字
        """
        images = sorted(Path(image_dir).glob("*.png")) + sorted(Path(image_dir).glob("*.jpg"))
        if not images:
            warn(f"图片目录为空: {image_dir}")
            return ""

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 检查 ffmpeg
        if not self._has_ffmpeg():
            warn("ffmpeg 未安装，降级到 moviepy")
            return self._fallback_moviepy(images, output_path, duration_per_image)

        info(f"🎬 FFmpeg 合成: {len(images)} 张图 → {output_path}")

        # Step 1: 图片序列 → 基础视频
        temp_video = str(Path(output_path).with_suffix(".raw.mp4"))
        self._images_to_video(images, temp_video, duration_per_image, transition)

        # Step 2: 叠加字幕
        if subtitle_texts:
            video_with_subs = str(Path(output_path).with_suffix(".subs.mp4"))
            self._add_subtitles(temp_video, video_with_subs, subtitle_texts, duration_per_image)
            temp_video = video_with_subs

        # Step 3: 叠加水印
        if watermark_text:
            video_with_wm = str(Path(output_path).with_suffix(".wm.mp4"))
            self._add_watermark(temp_video, video_with_wm, watermark_text)
            temp_video = video_with_wm

        # Step 4: 叠加音乐
        if music_path and Path(music_path).exists():
            video_with_music = str(Path(output_path).with_suffix(".music.mp4"))
            self._add_music(temp_video, music_path, video_with_music)
            # 清理中间步骤
            os.replace(video_with_music, output_path)
        else:
            os.replace(temp_video, output_path)

        # 清理临时文件
        for tmp in Path(output_path).parent.glob(f"{Path(output_path).stem}.*.mp4"):
            try: tmp.unlink()
            except: pass

        info(f"✅ 视频已合成: {output_path}")
        return output_path

    # ---------------------------------------------------------------
    # 内部步骤
    # ---------------------------------------------------------------

    def _images_to_video(self, images, output, duration, transition):
        """图片序列 → 视频 + 转场"""
        # 创建 concat 文件
        concat_file = str(Path(output).with_suffix(".concat.txt"))
        with open(concat_file, "w") as f:
            for img in images:
                f.write(f"file '{img.as_posix()}'\n")
                f.write(f"duration {duration}\n")
            # 最后一张重复一次（ffmpeg concat 需要）
            f.write(f"file '{images[-1].as_posix()}'\n")

        # 基础过滤器
        vf_parts = [
            f"fps={self.fps}",
            "scale=1920:1080:force_original_aspect_ratio=decrease",
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        ]

        # 转场效果
        if transition == "fade":
            vf_parts.append(f"fade=t=in:d=0.5,fade=t=out:d=0.5")
        elif transition == "zoom":
            vf_parts.append("zoompan=z='min(zoom+0.0015,1.1)':d=125")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-vf", ",".join(vf_parts),
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            output,
        ]
        self._run(cmd, "图片→视频")
        Path(concat_file).unlink(missing_ok=True)

    def _add_subtitles(self, input_video, output, texts, duration_per):
        """叠加硬字幕"""
        # 生成 SRT 字幕文件
        srt_path = str(Path(output).with_suffix(".srt"))
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, text in enumerate(texts):
                if not text: continue
                start = i * duration_per
                end = start + duration_per
                f.write(f"{i+1}\n")
                f.write(f"{self._fmt_time(start)} --> {self._fmt_time(end)}\n")
                f.write(f"{text}\n\n")

        cmd = [
            "ffmpeg", "-y", "-i", input_video,
            "-vf", f"subtitles={srt_path}:force_style='FontSize=28,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2'",
            "-c:v", "libx264", "-preset", "fast", output,
        ]
        self._run(cmd, "叠加字幕")
        Path(srt_path).unlink(missing_ok=True)

    def _add_watermark(self, input_video, output, text):
        """叠加水印"""
        cmd = [
            "ffmpeg", "-y", "-i", input_video,
            "-vf", f"drawtext=text='{text}':fontsize=20:fontcolor=white@0.5:x=w-tw-20:y=h-th-20",
            "-c:v", "libx264", "-preset", "fast", output,
        ]
        self._run(cmd, "叠加水印")

    def _add_music(self, input_video, music_path, output):
        """叠加背景音乐"""
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-i", music_path,
            "-filter_complex", "[1:a]volume=0.3[bgm];[0:a][bgm]amix=inputs=2:duration=first",
            "-c:v", "copy", "-shortest", output,
        ]
        self._run(cmd, "叠加音乐")

    def _fallback_moviepy(self, images, output, duration):
        """moviepy 降级方案"""
        from src.tools.composer import VideoComposer
        from src.models import Storyboard, Shot
        storyboard = Storyboard(script_title="composed")
        for img in images:
            storyboard.shots.append(Shot(scene_id=0, image_prompt="", motion_prompt="", image_path=str(img)))
        c = VideoComposer(fps=self.fps)
        return c.compose(storyboard, output_path=output, add_subtitles=False)

    # ---------------------------------------------------------------
    # 工具方法
    # ---------------------------------------------------------------

    @staticmethod
    def _has_ffmpeg() -> bool:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            return True
        except:
            return False

    @staticmethod
    def _run(cmd, label):
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except subprocess.CalledProcessError as e:
            warn(f"{label}失败: {e.stderr.decode()[:200] if e.stderr else str(e)}")

    @staticmethod
    def _fmt_time(seconds: int) -> str:
        h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d},000"
