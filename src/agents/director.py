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
# 知识库 Prompt 工程: Few-shot 示例提升 30-50% 输出质量
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

## Few-shot 参考示例

### 示例1: "一只猫在雨夜的便利店门口躲雨" (anime 风格)
{
  "title": "雨夜便利店",
  "logline": "一只流浪猫在雨夜找到的不只是避雨的地方，还有一个家。",
  "scenes": [
    {
      "scene_id": 1,
      "description": "雨夜街道全景，霓虹灯倒映在积水中，一只小猫蜷缩在便利店屋檐下",
      "visual_prompt": "A rainy Tokyo street at night, anime style, neon reflections on wet pavement, a small orange tabby cat huddled under a convenience store awning, warm light spilling from the store, cinematic composition, Studio Ghibli inspired",
      "motion_prompt": "镜头从高空缓缓下降，穿过雨幕，聚焦到小猫身上",
      "duration_sec": 5,
      "dialogue": "",
      "camera": "俯拍下降 → 中景"
    },
    {
      "scene_id": 2,
      "description": "便利店门打开，暖光洒出，一个女孩蹲下来看着小猫",
      "visual_prompt": "Convenience store door sliding open, anime style, warm golden light flooding out, silhouette of a young woman crouching down, the cat looking up with big reflective eyes, bokeh effect from rain, emotional moment",
      "motion_prompt": "门滑开的慢动作，光线逐渐照亮小猫的脸",
      "duration_sec": 4,
      "dialogue": "（轻声）你也在躲雨吗？",
      "camera": "低角度 → 特写猫脸"
    },
    {
      "scene_id": 3,
      "description": "女孩伸手，小猫犹豫后靠近，画面温馨",
      "visual_prompt": "Close-up of a hand reaching out to a hesitant cat, anime style, warm colors, rain droplets on glass in background, soft focus, emotional connection moment, Makoto Shinkai inspired lighting",
      "motion_prompt": "小猫从退缩到慢慢靠近，爪子踩在水面上的涟漪",
      "duration_sec": 3,
      "dialogue": "",
      "camera": "特写手 → 特写猫爪"
    },
    {
      "scene_id": 4,
      "description": "女孩抱着小猫走进便利店，门缓缓关上，雨继续下",
      "visual_prompt": "Wide shot of a convenience store at night, anime style, through the window we see a girl holding a cat at the counter, rain continues falling, warm interior light contrasting with cool blue exterior, peaceful ending",
      "motion_prompt": "镜头缓慢拉远，从店内到店外全景",
      "duration_sec": 5,
      "dialogue": "店员：欢迎光临——哦，还有一位小客人。",
      "camera": "全景拉远"
    }
  ]
}

### 示例2: "宇航员在荒芜星球上发现了一株植物" (cinematic 风格)
{
  "title": "最后的绿色",
  "logline": "在生命绝迹的星球上，一株幼苗重新点燃了希望。",
  "scenes": [
    {
      "scene_id": 1,
      "description": "广袤的红色荒漠，一个孤独的宇航员身影在远处行走",
      "visual_prompt": "Vast red desert landscape on an alien planet, cinematic style, a lone astronaut figure walking in the distance, dust storms in background, dramatic lighting from binary suns, 70mm film look, Christopher Nolan inspired",
      "motion_prompt": "缓慢横移镜头，跟随宇航员的身影",
      "duration_sec": 6,
      "dialogue": "",
      "camera": "极远景 → 横移跟拍"
    },
    {
      "scene_id": 2,
      "description": "宇航员停下，头盔面罩反射出一抹绿色",
      "visual_prompt": "Medium shot of astronaut stopping suddenly, cinematic style, helmet visor reflecting a tiny green sprout, red desert surrounding, dust particles floating, dramatic contrast, hyper-realistic",
      "motion_prompt": "镜头急速推进到面罩特写",
      "duration_sec": 3,
      "dialogue": "（呼吸声）这是...？",
      "camera": "中景急推 → 面罩特写"
    },
    {
      "scene_id": 3,
      "description": "宇航员跪下来，手套轻轻触碰岩石缝中的绿色幼苗",
      "visual_prompt": "Extreme close-up of a space glove gently touching a tiny green seedling growing from a rock crack, cinematic macro shot, red dust on green leaves, sun flare in background, emotional and hopeful, Terrence Malick style",
      "motion_prompt": "极慢速推近，焦点从手套移到幼苗",
      "duration_sec": 5,
      "dialogue": "（哽咽）你还活着...",
      "camera": "超特写"
    },
    {
      "scene_id": 4,
      "description": "宇航员跪在幼苗旁，抬头望向远方地平线上升起的蓝色地球",
      "visual_prompt": "Wide cinematic shot of astronaut kneeling beside a tiny plant, looking up at the horizon where a blue Earth rises, epic scale, golden hour lighting on Mars-like terrain, hopeful atmosphere, inspired by Interstellar",
      "motion_prompt": "镜头从幼苗缓缓上摇，到宇航员，再到地球",
      "duration_sec": 6,
      "dialogue": "",
      "camera": "微距上摇 → 大远景"
    }
  ]
}

## 创作要求
1. 剧本适合 30-90 秒短视频
2. 场景数 4-8 个，每个 3-8 秒
3. visual_prompt 用英文，参考示例的详细程度（风格/光线/构图/参考导演）
4. motion_prompt 用中文描述动效
5. 有明确的起承转合
6. 最后一个场景要有记忆点（反转/感动/幽默）
7. 参考示例的质量和格式，但故事必须原创"""


class DirectorAgent:
    """剧本导演 Agent"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()
        self.use_mock = not self.llm.api_key or "mock" in self.llm.api_key.lower()
        self._bible_context = ""  # 故事圣经上下文（Pipeline 注入）

    def create_script(self, idea: str, style: str = "cinematic") -> Script:
        """把用户想法变成剧本"""
        if self.use_mock:
            return self._create_mock_script(idea, style)

        # 构建系统提示词：基础 + 圣经上下文
        system = DIRECTOR_SYSTEM
        if self._bible_context:
            system += f"\n\n{self._bible_context}"
            system += "\n\n⚠️ 重要：你的剧本必须严格遵循以上「故事圣经」中的设定。角色名、地点、道具、风格必须和已有设定一致。"

        print(f"🎬 [Director] 正在创作剧本...")
        print(f"   想法: {idea}  风格: {style}  模型: {self.llm.name}")
        if self._bible_context:
            print(f"   📖 已注入故事圣经上下文")

        raw = self.llm.chat(system, f"创意想法：{idea}\n视觉风格：{style}\n请生成完整剧本。")
        script = self._parse_script(raw)
        script.raw_text = raw
        self._print_script(script)
        return script

    def _create_mock_script(self, idea: str, style: str = "cinematic") -> Script:
        """Mock 模式：使用模板生成个性化剧本（无需 API Key）"""
        print(f"🎬 [Director-Mock] 生成个性化剧本...")
        print(f"   想法: {idea}  风格: {style}")

        # 从 idea 中提取关键词
        import re
        words = re.split(r'[，,、\s在的与和了去来到着]', idea)
        keywords = [w.strip() for w in words if len(w.strip()) >= 2][:3]
        subject = keywords[-1] if keywords else idea[:10]
        location_desc = f"一个{idea}的世界" if len(idea) < 20 else idea

        scenes = [
            Scene(1, f"开场：{subject}登场，{style}风格的环境氛围",
                  f"A wide establishing shot introducing {subject}, {style} style, detailed environment showing {location_desc}, dramatic lighting, highly detailed",
                  "镜头缓缓推进，从远景到中景，引入主角",
                  4, "", "远景 → 中景"),
            Scene(2, f"转折：{subject}遇到意外挑战",
                  f"{subject} encounters an unexpected challenge, {style} style, dynamic composition, tension in the air, close-up on {subject}'s face",
                  "快速切换到特写，表现主角的反应",
                  3, f"（惊讶）这是...？", "特写"),
            Scene(3, f"发展：{subject}在{style}氛围中做出关键选择",
                  f"{subject} makes a crucial decision, {style} style, motion blur, intense atmosphere, {location_desc} in background",
                  "跟拍镜头，跟随主角的动作",
                  5, "", "跟拍"),
            Scene(4, f"高潮：{subject}面对核心挑战的关键时刻",
                  f"The climactic moment of {idea}, {style} style, epic composition, dramatic light rays, {subject} at center, emotional peak",
                  "慢动作，旋转镜头围绕主角",
                  6, f"（坚定）这就是我的选择！", "360°环绕"),
            Scene(5, f"结尾：{subject}的故事留下余韵",
                  f"The final scene of {idea}, {style} style, peaceful yet memorable, golden hour lighting, {subject} in the distance, hopeful atmosphere",
                  "镜头缓缓拉远，主角的身影逐渐变小",
                  5, "", "远景拉远"),
        ]

        script = Script(
            title=f"《{idea[:15]}》" if len(idea) <= 15 else f"《{idea[:12]}...》",
            logline=f"一个关于{idea}的故事——在{style}风格下展开。",
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
