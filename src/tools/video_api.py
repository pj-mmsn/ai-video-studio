"""
真实视频生成 API 集成
============================================================
RunwayML Gen-3 / Pika Labs / ComfyUI — 三种后端统一接口。

RunwayML: https://docs.runwayml.com
Pika: https://pika.art/api
ComfyUI: 本地部署，HTTP API
"""
from __future__ import annotations

import os
import time
import json
import base64
import urllib.request
from pathlib import Path
from typing import Optional

from src.logging_config import info, warn


class VideoAPIClient:
    """视频生成 API 统一客户端"""

    def __init__(self, backend: str = "runway"):
        self.backend = backend
        self.runway_key = os.getenv("RUNWAY_API_KEY", "")
        self.pika_key = os.getenv("PIKA_API_KEY", "")
        self.comfyui_url = os.getenv("COMFYUI_URL", "http://localhost:8188")

    # ================================================================
    # RunwayML Gen-3
    # ================================================================

    def runway_generate(
        self,
        image_path: str,
        prompt: str,
        duration: int = 5,
        wait: bool = True,
    ) -> Optional[str]:
        """RunwayML Gen-3: 图生视频

        API: POST https://api.runwayml.com/v1/generate
        """
        if not self.runway_key:
            warn("RUNWAY_API_KEY 未设置，跳过 RunwayML 调用")
            return None

        info(f"📡 RunwayML: {prompt[:60]}...")

        # 读取图片并 Base64 编码
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        body = json.dumps({
            "model": "gen3",
            "promptImage": img_b64,
            "promptText": prompt,
            "duration": duration,
            "watermark": False,
        }).encode()

        req = urllib.request.Request(
            "https://api.runwayml.com/v1/generate",
            data=body,
            headers={
                "Authorization": f"Bearer {self.runway_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                task_id = result.get("id", "")

            if wait and task_id:
                return self._wait_runway(task_id)

            return task_id
        except Exception as e:
            warn(f"RunwayML 调用失败: {e}")
            return None

    def _wait_runway(self, task_id: str, timeout: int = 300) -> Optional[str]:
        """轮询 RunwayML 任务状态"""
        start = time.time()
        while time.time() - start < timeout:
            req = urllib.request.Request(
                f"https://api.runwayml.com/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self.runway_key}"},
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())

            status = data.get("status", "")
            if status == "SUCCEEDED":
                url = data.get("output", {}).get("video", "")
                info(f"✅ RunwayML 完成: {url[:60]}...")
                return url
            elif status == "FAILED":
                warn(f"RunwayML 任务失败: {data.get('error','')}")
                return None

            info(f"   RunwayML 处理中... ({status})")
            time.sleep(5)

        warn(f"RunwayML 超时 ({timeout}s)")
        return None

    # ================================================================
    # Pika Labs
    # ================================================================

    def pika_generate(
        self,
        image_path: str,
        prompt: str,
        duration: int = 5,
    ) -> Optional[str]:
        """Pika Labs: 图生视频"""
        if not self.pika_key:
            warn("PIKA_API_KEY 未设置")
            return None

        info(f"📡 Pika: {prompt[:60]}...")
        # Pika API 需要 multipart upload
        # 简化实现：返回占位
        warn("Pika API 接入开发中，当前返回占位")
        return "pika_task_placeholder"

    # ================================================================
    # ComfyUI（本地）
    # ================================================================

    def comfyui_generate(
        self,
        workflow_json: str,
        wait: bool = True,
    ) -> Optional[str]:
        """ComfyUI: 提交 workflow，轮询结果

        workflow_json: ComfyUI workflow JSON 文件路径或 JSON 字符串
        """
        info(f"📡 ComfyUI: {self.comfyui_url}")

        # 加载 workflow
        if os.path.exists(workflow_json):
            workflow = json.loads(Path(workflow_json).read_text())
        else:
            workflow = json.loads(workflow_json)

        # 提交
        body = json.dumps({"prompt": workflow}).encode()
        try:
            req = urllib.request.Request(
                f"{self.comfyui_url}/prompt",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                prompt_id = result.get("prompt_id", "")

            if wait and prompt_id:
                return self._wait_comfyui(prompt_id)

            return prompt_id
        except Exception as e:
            warn(f"ComfyUI 调用失败: {e}（ComfyUI 是否在 {self.comfyui_url} 运行？）")
            return None

    def _wait_comfyui(self, prompt_id: str, timeout: int = 120) -> Optional[str]:
        """轮询 ComfyUI 结果"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(f"{self.comfyui_url}/history/{prompt_id}")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())

                if prompt_id in data:
                    outputs = data[prompt_id].get("outputs", {})
                    # 找到第一个视频输出
                    for node_id, node_output in outputs.items():
                        videos = node_output.get("videos", []) or node_output.get("gifs", [])
                        if videos:
                            video_path = os.path.join(
                                self.comfyui_url.replace("http://", "").split(":")[0],
                                "output", videos[0].get("filename", "")
                            )
                            info(f"✅ ComfyUI 完成")
                            return video_path

                time.sleep(2)
            except Exception:
                time.sleep(2)

        warn(f"ComfyUI 超时 ({timeout}s)")
        return None


# ================================================================
# 便捷函数
# ================================================================

def generate_video(
    image_path: str,
    prompt: str,
    backend: str = "runway",
    duration: int = 5,
) -> Optional[str]:
    """一行调用生成视频"""
    client = VideoAPIClient(backend=backend)

    if backend == "runway":
        return client.runway_generate(image_path, prompt, duration)
    elif backend == "pika":
        return client.pika_generate(image_path, prompt, duration)
    elif backend == "comfyui":
        # ComfyUI 需要预定义的 workflow
        workflow_path = os.getenv("COMFYUI_WORKFLOW", "workflows/video_gen.json")
        return client.comfyui_generate(workflow_path)
    else:
        warn(f"未知后端: {backend}")
        return None
