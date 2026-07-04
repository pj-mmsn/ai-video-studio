"""
StoryBible — 故事圣经上下文管理器
============================================================
解决长片中"前后不搭"的核心问题。

工作原理：
    1. 每完成一个场景，LLM 提取关键信息（角色、道具、地点、剧情点）
    2. 存入 story_bible 表
    3. 生成下一个场景时，把圣经文本注入到 Director 的 system prompt 中
    4. 这样场景 50 也知道场景 1 的主角叫什么、穿什么、有什么道具

类比：像电影编剧的"人物小传"和"场景卡片"，确保全片一致。
"""
from __future__ import annotations

import json

from src.models import LLMClient, Script, Scene
from src.db.repository import ProjectRepository

# 提取系统提示词——让 LLM 从场景中提取关键信息
EXTRACT_SYSTEM = """你是一位细心的剧本分析员。请从以下场景描述中提取关键信息，
用于维护"故事圣经"——确保整部作品的设定前后一致。

## 提取类别
1. character（角色）：名字、外貌特征、性格、服装
2. location（场景设定）：地点名称、环境特征、时间（白天/夜晚）
3. prop（关键道具）：重要物品、其特征和用途
4. plot_point（剧情要点）：本场景发生了什么事、角色做出了什么决定
5. style_rule（视觉风格规则）：颜色基调、光线风格、镜头偏好

## 输出格式（严格 JSON）
{
  "entries": [
    {"category": "character", "key": "角色名/特征", "value": "具体描述"},
    {"category": "location", "key": "地点名", "value": "环境描述"},
    ...
  ]
}

## 规则
- 只提取本场景新出现的信息，不要重复已有设定
- 如果场景没有新信息，返回 {"entries": []}
- value 要具体，不要模糊（"一个男孩"→ "12岁男孩，戴圆框眼镜，穿蓝色卫衣"）
"""


class StoryBible:
    """故事圣经——维护跨场景一致性

    使用方式：
        bible = StoryBible(repo, llm_client)
        bible.update_from_script(script)       # 从剧本提取所有设定
        context = bible.get_context_text()     # 获取圣经文本
        # 把 context 注入 Director prompt，确保新场景和已有设定一致
    """

    def __init__(self, repo: ProjectRepository, llm_client: LLMClient = None):
        self.repo = repo
        self.llm = llm_client or LLMClient()
        self.use_mock = not self.llm.api_key or "mock" in self.llm.api_key.lower()

    def update_from_script(self, script: Script) -> int:
        """从完整剧本中提取所有设定，写入圣经

        Returns: 新增条目数
        """
        if self.use_mock:
            # Mock：从场景描述中简单提取
            return self._update_mock(script)

        total = 0
        for scene in script.scenes:
            count = self._extract_from_scene(scene)
            total += count

        # 强制记录核心元数据：标题和梗概
        self.repo.save_bible_entry("plot_point", "标题", script.title, 0)
        self.repo.save_bible_entry("plot_point", "梗概", script.logline, 0)

        print(f"   📖 故事圣经: 新增 {total} 条设定")
        return total

    def _extract_from_scene(self, scene: Scene) -> int:
        """用 LLM 从一个场景中提取关键信息"""
        prompt = f"""
场景 {scene.scene_id}:
描述: {scene.description}
视觉: {scene.visual_prompt}
动效: {scene.motion_prompt}
台词: {scene.dialogue or '无'}
镜头: {scene.camera}
"""
        try:
            raw = self.llm.chat(EXTRACT_SYSTEM, prompt)

            # 解析 JSON
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]
            data = json.loads(json_str.strip())

            count = 0
            for entry in data.get("entries", []):
                self.repo.save_bible_entry(
                    category=entry.get("category", "other"),
                    key=entry.get("key", ""),
                    value=entry.get("value", ""),
                    source_scene=scene.scene_id,
                )
                count += 1
            return count
        except Exception as e:
            print(f"   ⚠️  场景{scene.scene_id}圣经提取失败: {e}")
            return 0

    def _update_mock(self, script: Script) -> int:
        """Mock 模式：从场景描述中简单提取"""
        count = 0
        for scene in script.scenes:
            if "场景设定" not in str(scene.description) and scene.camera:
                self.repo.save_bible_entry(
                    "style_rule", f"场景{scene.scene_id}镜头",
                    scene.camera, scene.scene_id
                )
                count += 1
            if scene.description:
                # 首个场景：标注主场景
                if scene.scene_id == 1:
                    self.repo.save_bible_entry(
                        "location", "开场场景", scene.description[:50], scene.scene_id
                    )
                    count += 1

        self.repo.save_bible_entry("plot_point", "标题", script.title, 0)
        self.repo.save_bible_entry("plot_point", "梗概", script.logline, 0)
        print(f"   📖 故事圣经 [Mock]: {count + 2} 条基础设定")
        return count + 2

    def get_context_text(self) -> str:
        """获取故事圣经文本——注入 Director prompt 用"""
        return self.repo.get_bible_text()

    def get_character_count(self) -> int:
        """已记录的角色数"""
        try:
            row = self.repo.conn.execute(
                "SELECT COUNT(*) FROM story_bible WHERE project_id=? AND category='character'",
                (self.repo.project_id,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0
