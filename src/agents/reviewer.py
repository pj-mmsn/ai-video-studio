"""
Reviewer Agent — 质量审查员
============================================================
知识库指出(Multi-Agent 文档)：CrewAI 层级管理模式中，每个产出
都要经过 Reviewer 审查，不合格的退回修改。

本项目加入 Reviewer 作为可选 Stage 4，插入到每个阶段之后，
形成"产出→审查→修正→放行"的反馈循环。

对比改进前:
    改进前: Director → Storyboard → Videographer（纯线性，无反馈）
    改进后: Director → Review → Storyboard → Review → Videographer → Review（有反馈）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.models import LLMClient, Script, Storyboard, Shot, VideoClip

# 审查员系统提示词
REVIEWER_SYSTEM = """你是一位严格的影视质控专家。你的任务是审查 AI 生成的视频制作产物，
判断质量是否过关，并给出具体的修改建议。

## 审查标准

### 剧本审查
1. 场景数是否在 4-8 个之间？
2. 是否有明确的起承转合？
3. visual_prompt 是否足够详细（至少 20 个词，包含风格/光线/构图）？
4. 最后一个场景是否有记忆点（反转/感动/幽默）？

### 分镜审查
1. visual_prompt 和 motion_prompt 是否匹配？
2. 镜头语言（camera）描述是否合理？
3. 场景之间是否有视觉连贯性？

### 视频审查
1. 动效描述是否可行？
2. 时长分配是否合理？

## 输出格式（严格 JSON）
{
  "passed": true/false,
  "score": 1-10,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}

如果 passed=false，issues 必须具体指明哪个场景有什么问题、怎么改。"""


@dataclass
class ReviewResult:
    """审查结果"""
    passed: bool
    score: int
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    target_stage: str = ""      # 审查的是哪个阶段

    def report(self) -> str:
        status = "✅ 通过" if self.passed else "❌ 需修改"
        return f"[{self.target_stage}] {status} 评分:{self.score}/10"


class ReviewerAgent:
    """质量审查员 Agent

    可在任意阶段产出后插入，进行质量把关。
    不合格的产出会返回修改建议，由前一阶段 Agent 重试。
    """

    def __init__(self, llm_client: LLMClient = None, strictness: int = 6):
        """
        Args:
            llm_client: 审查用 LLM（可以和 Director 不同模型，如用更便宜的模型做审查）
            strictness: 严格度 1-10，低于此分数的产出会被打回
        """
        self.llm = llm_client or LLMClient()
        self.strictness = strictness
        self.use_mock = not self.llm.api_key or "mock" in self.llm.api_key.lower()
        self.history: list[ReviewResult] = []  # 审查历史

    # ================================================================
    # 审查入口：按产物类型分发
    # ================================================================

    def review_script(self, script: Script) -> ReviewResult:
        """审查剧本"""
        content = f"""
剧本标题: {script.title}
梗概: {script.logline}
场景数: {len(script.scenes)}

场景详情:
{self._format_scenes(script)}
"""
        return self._review("剧本", content)

    def review_storyboard(self, storyboard: Storyboard) -> ReviewResult:
        """审查分镜"""
        content = f"分镜标题: {storyboard.script_title}\n"
        for shot in storyboard.shots:
            content += f"""
场景{shot.scene_id}:
  图像提示词: {shot.image_prompt}
  动效提示词: {shot.motion_prompt}
"""
        return self._review("分镜", content)

    def review_clips(self, clips: list[VideoClip], storyboard: Storyboard) -> ReviewResult:
        """审查视频片段"""
        content = f"视频片段数: {len(clips)}\n"
        for clip in clips:
            content += f"  场景{clip.scene_id}: {clip.prompt[:100]}... [{clip.duration_sec}s]\n"
        return self._review("视频", content)

    # ================================================================
    # 通用审查逻辑
    # ================================================================

    def _review(self, stage_name: str, content: str) -> ReviewResult:
        if self.use_mock:
            # Mock 模式：一律通过
            result = ReviewResult(
                passed=True, score=8,
                suggestions=["Mock 模式自动通过"],
                target_stage=stage_name,
            )
            self.history.append(result)
            print(f"   🔍 [Reviewer-Mock] {result.report()}")
            return result

        print(f"   🔍 [Reviewer] 审查{stage_name}中...")
        raw = self.llm.chat(REVIEWER_SYSTEM, f"请审查以下{stage_name}内容:\n\n{content}")

        # 解析 JSON
        import json
        try:
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]
            data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            data = {"passed": True, "score": 5, "issues": [], "suggestions": ["JSON解析失败，默认通过"]}

        result = ReviewResult(
            passed=data.get("passed", True) and data.get("score", 10) >= self.strictness,
            score=data.get("score", 5),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            target_stage=stage_name,
        )
        self.history.append(result)
        print(f"   🔍 [Reviewer] {result.report()}")
        if result.issues:
            for issue in result.issues:
                print(f"      ⚠️  {issue}")
        return result

    def _format_scenes(self, script) -> str:
        lines = []
        for s in script.scenes:
            lines.append(f"场景{s.scene_id}: {s.description}")
            lines.append(f"  视觉: {s.visual_prompt[:80]}...")
            lines.append(f"  动效: {s.motion_prompt}")
            lines.append(f"  镜头: {s.camera}")
        return "\n".join(lines)

    def summary(self) -> str:
        """审查总结"""
        if not self.history:
            return "无审查记录"
        passed = sum(1 for r in self.history if r.passed)
        avg = sum(r.score for r in self.history) / len(self.history)
        return f"审查 {len(self.history)} 次 | 通过 {passed} | 均分 {avg:.1f}"
