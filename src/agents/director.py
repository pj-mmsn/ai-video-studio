"""
Stage 1: Director Agent — 剧本导演
============================================================
用推理/创意模型，把用户的一句话想法扩展成完整剧本。

输入: "一只猫在太空站冒险"
输出: 结构化剧本（标题、梗概、场景列表、每个场景的视觉/动效提示词）

为什么用推理模型？
    编剧需要逻辑连贯性——人物动机、场景过渡、叙事节奏。
    推理模型（GPT-4o/DeepSeek-R1）在这些方面远优于普通模型。
"""
from __future__ import annotations

import json
import re

from src.models import LLMClient, Script, Scene

# 导演系统提示词——关键！决定了剧本的质量和格式
DIRECTOR_SYSTEM = """你是一位资深动画导演和编剧。你的任务是把用户的想法扩展成一个完整的短视频剧本。

## 输出格式（严格 JSON）
{
  "title": "短片标题",
  "logline": "一句话梗概（吸引人，30字以内）",
  "scenes": [
    {
      "scene_id": 1,
      "description": "场景画面描述（中文，50字内）",
      "visual_prompt": "给AI绘图模型的英文提示词（详细描述画面、光线、构图、风格）",
      "motion_prompt": "动效描述（镜头运动、物体运动、转场）",
      "duration_sec": 5,
      "dialogue": "台词或旁白（可空）",
      "camera": "镜头语言（特写/中景/全景/跟拍/俯拍等）"
    }
  ]
}

## 创作要求
1. 剧本适合 30-90 秒短视频
2. 场景数 4-8 个，每个 3-8 秒
3. visual_prompt 用英文，详细描述风格（cinematic/anime/3D render/watercolor等）
4. motion_prompt 用中文描述动效
5. 有明确的起承转合
6. 最后一个场景要有记忆点（反转/感动/幽默）"""


class DirectorAgent:
    """剧本导演 Agent"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()
        self.use_mock = not self.llm.api_key or "mock" in self.llm.api_key.lower()

    def create_script(self, idea: str, style: str = "cinematic") -> Script:
        """把用户想法变成剧本"""
        if self.use_mock:
            return self._create_mock_script(idea, style)

        print(f"🎬 [Director] 正在创作剧本...")
        print(f"   想法: {idea}")
        print(f"   风格: {style}")
        print(f"   模型: {self.llm.name}")

        raw = self.llm.chat(DIRECTOR_SYSTEM, f"创意想法：{idea}\n视觉风格：{style}\n请生成完整剧本。")
        script = self._parse_script(raw)
        script.raw_text = raw
        self._print_script(script)
        return script

    def _create_mock_script(self, idea: str, style: str = "cinematic") -> Script:
        """Mock 模式：生成示例剧本（无需 API Key）"""
        print(f"🎬 [Director-Mock] 生成示例剧本...")
        print(f"   想法: {idea}")
        print(f"   风格: {style}")

        scenes = [
            Scene(1, "开场：主角登场，环境氛围铺垫",
                  f"A wide establishing shot of {idea}, {style} style, dramatic lighting, highly detailed",
                  "镜头缓缓推进，从远景到中景，引入主角",
                  4, "", "远景 → 中景"),
            Scene(2, "冲突/转折：意外发生",
                  f"The protagonist encounters an unexpected challenge in {idea}, {style} style, dynamic composition, tension",
                  "快速切换到特写，表现主角的惊讶表情",
                  3, "（惊讶）这是...？", "特写"),
            Scene(3, "发展：主角做出决定",
                  f"The protagonist takes action, {idea}, {style} style, motion blur, intense",
                  "跟拍镜头，跟随主角的动作",
                  5, "", "跟拍"),
            Scene(4, "高潮：关键对决/揭示",
                  f"The climactic moment of {idea}, {style} style, epic composition, dramatic light rays",
                  "慢动作，旋转镜头围绕主角",
                  6, "（坚定）我必须这样做！", "360°环绕"),
            Scene(5, "结尾：新平衡，留下记忆点",
                  f"The final scene of {idea}, {style} style, peaceful yet memorable, golden hour lighting",
                  "镜头缓缓拉远，主角的身影逐渐变小",
                  5, "", "远景拉远"),
        ]

        script = Script(
            title=f"《{idea[:15]}...》" if len(idea) > 15 else f"《{idea}》",
            logline=f"一个关于{idea}的故事。",
            scenes=scenes,
        )
        self._print_script(script)
        return script

    def _print_script(self, script: Script):
        print(f"   ✅ 剧本完成:《{script.title}》 {len(script.scenes)} 个场景")
        for s in script.scenes:
            print(f"      场景{s.scene_id}: {s.description[:50]}... [{s.duration_sec}s]")

    def _parse_script(self, raw: str) -> Script:
        """从 LLM 输出中提取 JSON 并解析为 Script"""
        # 提取 JSON 块
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0]

        try:
            data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            # LLM 格式不规范时的兜底
            print("   ⚠️  JSON 解析失败，使用原始文本")
            return Script(
                title="未命名短片",
                logline=raw[:100],
                raw_text=raw,
            )

        scenes = []
        for s in data.get("scenes", []):
            scenes.append(Scene(
                scene_id=s.get("scene_id", len(scenes) + 1),
                description=s.get("description", ""),
                visual_prompt=s.get("visual_prompt", ""),
                motion_prompt=s.get("motion_prompt", ""),
                duration_sec=s.get("duration_sec", 5),
                dialogue=s.get("dialogue", ""),
                camera=s.get("camera", ""),
            ))

        return Script(
            title=data.get("title", "未命名短片"),
            logline=data.get("logline", ""),
            scenes=scenes,
        )
