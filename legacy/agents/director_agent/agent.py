"""
Director Agent — 独立包
============================================================
只通过 StudioDB 通信：
  输入: 读 sections 表（Novelist 写入的小说章节）
  输出: 写 scenes 表（Storyboard 读取的剧本场景）

独立启动: python -m src.agents.director_agent.cli --project my_novel
"""
from app.config import load_config
from src.models.llm_client import chat
from src.db.studio_db import StudioDB

DIRECTOR_SYSTEM = """你是一位资深影视编剧。把小说章节改编为视频剧本场景。

对每个场景输出 JSON:
{
  "scene_number": 1,
  "description": "场景描述（中文30字内）",
  "visual_prompt": "给AI绘图的英文提示词（详细描述画面、光线、构图、风格）",
  "motion_prompt": "动效描述（镜头运动、物体运动）",
  "dialogue": "台词（可空）",
  "camera": "镜头语言（特写/中景/全景）",
  "duration_sec": 5
}

要求:
- 每章改编为2-4个场景
- visual_prompt 用英文，包含风格/光线/构图
- 场景之间视觉连贯"""


class DirectorAgent:
    """剧本导演——读小说，写剧本"""

    def __init__(self, project_id: str, config: dict = None):
        self.project_id = project_id
        self.config = config or load_config()
        self.db = StudioDB(project_id)

    def adapt(self, section_ids: list[int] = None) -> int:
        """将指定章节（或所有未改编章节）改编为剧本场景

        Returns: 新增场景数
        """
        sections = self.db.get_sections()
        if not sections:
            print("📭 没有小说章节，请先运行 Novelist")
            return 0

        # 找出还没被改编的章节
        existing_scenes = {s["source_section_id"] for s in self.db.get_scenes()}
        new_sections = [s for s in sections if s["id"] not in existing_scenes]
        if section_ids:
            new_sections = [s for s in new_sections if s["id"] in section_ids]

        if not new_sections:
            print("✅ 所有章节已改编")
            return 0

        total = 0
        # 获取圣经上下文
        bible = self.db.get_bible()
        bible_text = "\n".join(f"[{b['category']}] {b['key']}: {b['value']}" for b in bible)

        for sec in new_sections:
            print(f"🎬 改编: 第{sec['volume']}卷第{sec['chapter']}章第{sec['section']}节")

            user = f"请将以下小说内容改编为视频剧本场景:\n\n{sec['content'][:3000]}"
            if bible_text:
                user = f"故事背景:\n{bible_text}\n\n{user}"

            raw = chat(self.config, DIRECTOR_SYSTEM, user)

            # 解析 JSON 场景列表
            scenes = self._parse_scenes(raw)
            for s in scenes:
                self.db.save_scene(
                    scene_number=s.get("scene_number", total + 1),
                    description=s.get("description", ""),
                    visual_prompt=s.get("visual_prompt", ""),
                    motion_prompt=s.get("motion_prompt", ""),
                    dialogue=s.get("dialogue", ""),
                    camera=s.get("camera", ""),
                    duration=s.get("duration_sec", 5),
                    source_section_id=sec["id"],
                )
                total += 1

            print(f"   ✅ {len(scenes)} 个场景")

        self.db.update_status(f"adapted_{total}_scenes")
        return total

    def _parse_scenes(self, raw: str) -> list[dict]:
        import json
        try:
            json_str = raw
            if "```json" in raw: json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw: json_str = raw.split("```")[1].split("```")[0]
            data = json.loads(json_str.strip())
            if isinstance(data, dict): return [data]
            if isinstance(data, list): return data
        except json.JSONDecodeError:
            pass
        # 降级：创建一个场景
        return [{"scene_number": 1, "description": raw[:100], "visual_prompt": raw[:200], 
                 "motion_prompt": "", "dialogue": "", "camera": "中景", "duration_sec": 5}]

    def close(self): self.db.close()
