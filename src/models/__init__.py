"""
模型客户端层 — 封装三种模型的 API 调用
============================================================
每种模型一个 Client 类，统一接口，可替换。
支持"真实 API"和"Mock 模式"两种运行方式。
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from config import config


# ================================================================
# 数据结构
# ================================================================

@dataclass
class Script:
    """剧本产物"""
    title: str
    logline: str                        # 一句话梗概
    scenes: list[Scene] = field(default_factory=list)
    raw_text: str = ""

    def summary(self) -> str:
        return f"《{self.title}》| {len(self.scenes)} 个场景 | {self.logline[:60]}..."


@dataclass
class Scene:
    """一个场景/镜头"""
    scene_id: int
    description: str                    # 场景描述
    visual_prompt: str                  # 给图像模型的提示词
    motion_prompt: str                  # 给视频模型的动效提示词
    duration_sec: int = 5
    dialogue: str = ""
    camera: str = ""                    # 镜头语言


@dataclass
class Storyboard:
    """分镜产物"""
    script_title: str
    shots: list[Shot] = field(default_factory=list)


@dataclass
class Shot:
    """一个分镜镜头"""
    scene_id: int
    image_prompt: str                   # 实际发给图像模型的 prompt
    image_path: Optional[str] = None    # 生成的图片路径
    image_url: Optional[str] = None     # 或图片 URL
    motion_prompt: str = ""


@dataclass
class VideoClip:
    """一段视频"""
    scene_id: int
    video_path: Optional[str] = None
    video_url: Optional[str] = None
    duration_sec: int = 5
    prompt: str = ""


# ================================================================
# 模型客户端接口
# ================================================================

class BaseModelClient(ABC):
    """模型客户端基类"""
    def __init__(self, model_name: str, api_key: str = ""):
        self.model_name = model_name
        self.api_key = api_key

    @property
    def name(self) -> str:
        return self.model_name


# ================================================================
# Stage 1: 推理模型 (Director)
# ================================================================

class LLMClient(BaseModelClient):
    """推理/创意模型客户端 — 用于生成剧本

    支持所有 OpenAI 兼容接口的推理模型：
        - GPT-4o / GPT-4-turbo
        - DeepSeek-R1 / DeepSeek-V3
        - Claude 3.5 Sonnet (via 兼容接口)
        - 智谱 GLM-4
    """

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        _api_key = api_key or config.director.api_key
        _base_url = base_url or config.director.base_url
        super().__init__(model or config.director.model, _api_key)
        self.base_url = _base_url
        # 判断是否是 Anthropic 兼容接口（/anthropic 端点）
        self._use_anthropic = "/anthropic" in _base_url
        if not self._use_anthropic:
            self.client = OpenAI(api_key=_api_key, base_url=_base_url)

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = None) -> str:
        """调用推理模型生成文本"""
        if self._use_anthropic:
            return self._chat_anthropic(system_prompt, user_prompt, temperature)
        return self._chat_openai(system_prompt, user_prompt, temperature)

    def _chat_openai(self, system_prompt, user_prompt, temperature):
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature or config.director.temperature,
        )
        return response.choices[0].message.content or ""

    def _chat_anthropic(self, system_prompt, user_prompt, temperature):
        """用 Anthropic Messages API 格式调用"""
        import urllib.request, json

        body = json.dumps({
            "model": self.model_name,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 4096,
            "temperature": temperature or config.director.temperature,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            content = data.get("content", [])
            # Anthropic 返回多个 content 块(thinking/text)，取 text 类型
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return texts[0] if texts else ""


# ================================================================
# Stage 2: 图像生成模型 (Storyboard)
# ================================================================

class ImageGenClient(BaseModelClient):
    """图像生成模型客户端 — 用于生成分镜图

    支持：
        - DALL-E 3 (OpenAI)
        - Stable Diffusion (via Replicate / ComfyUI)
        - Midjourney (via API wrapper)
    """

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        _api_key = api_key or config.storyboard.api_key
        super().__init__(model or config.storyboard.model, _api_key)
        self.client = OpenAI(
            api_key=_api_key,
            base_url=base_url or config.storyboard.base_url,
        )

    def generate(self, prompt: str, size: str = None) -> str:
        """生成一张图片，返回 URL"""
        try:
            response = self.client.images.generate(
                model=self.model_name,
                prompt=prompt,
                size=size or config.storyboard.image_size,
                n=1,
                quality="standard",
            )
            return response.data[0].url or ""
        except Exception as e:
            raise RuntimeError(f"图像生成失败 [{self.model_name}]: {e}")

    def generate_mock(self, prompt: str, output_path: str) -> str:
        """Mock 模式：生成占位图片（不需要 API）"""
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        img = Image.new("RGB", (1024, 1024), color=(30, 30, 40))
        draw = ImageDraw.Draw(img)

        # 画场景编号框
        draw.rectangle([20, 20, 1004, 1004], outline=(80, 80, 100), width=3)
        draw.text((40, 40), f"🎬 STORYBOARD", fill=(200, 200, 220))

        # 写提示词
        wrapped = textwrap.wrap(prompt[:200], width=50)
        y = 100
        for line in wrapped[:10]:
            draw.text((40, y), line, fill=(180, 180, 200))
            y += 30

        # 画模拟分镜框
        draw.rectangle([100, 400, 924, 900], outline=(100, 100, 130), width=2)
        draw.text((450, 620), "📷", fill=(150, 150, 170))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)
        return output_path


# ================================================================
# Stage 3: 视频生成模型 (Videographer)
# ================================================================

class VideoGenClient(BaseModelClient):
    """视频生成模型客户端 — 用于制作视频片段

    支持：
        - RunwayML Gen-3
        - Pika Labs
        - OpenAI Sora (未来)
        - 本地 ComfyUI + AnimateDiff
    """

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        _api_key = api_key or config.videographer.api_key
        super().__init__(model or config.videographer.model, _api_key)
        self.base_url = base_url or config.videographer.base_url

    def generate(self, image_path: str, motion_prompt: str, duration: int = None) -> str:
        """从图片生成视频片段，返回视频路径或 URL

        当前为 Mock 实现。接入真实 API 时替换此方法：
            - RunwayML: POST https://api.runwayml.com/v1/generate
            - Pika: POST https://api.pika.art/v1/generate
        """
        # 尝试调用真实 API
        if self.api_key and "mock" not in self.api_key.lower():
            # TODO: 接入 RunwayML / Pika API
            pass

        # Mock 实现：生成静态帧占位
        return self._generate_mock(image_path, motion_prompt, duration)

    def _generate_mock(self, image_path: str, motion_prompt: str, duration: int = None) -> str:
        """Mock：把分镜图作为视频的静态帧保存"""
        import shutil
        from pathlib import Path

        dur = duration or config.videographer.duration
        output = Path(config.output_dir) / "video" / f"scene_{int(time.time())}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)

        # 简单：复制图片作为"视频"占位
        if image_path and Path(image_path).exists():
            shutil.copy(image_path, output.with_suffix(".jpg"))

        # 生成占位元数据
        Path(str(output) + ".meta.json").write_text(json.dumps({
            "prompt": motion_prompt,
            "duration_sec": dur,
            "source_image": image_path,
            "status": "mock",
        }, ensure_ascii=False, indent=2))

        return str(output)


# 便捷导入
from pathlib import Path
from config import config as _cfg  # noqa: E402
