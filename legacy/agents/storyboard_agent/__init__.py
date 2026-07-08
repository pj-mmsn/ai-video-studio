"""
StoryboardAgent (DB-backed) — 备用架构
=======================================
通过 StudioDB 读取 scenes 表、写入 shots 表的独立版本。
与 src/agents/storyboard.py（Pipeline 使用的内存版）是两套不同的架构。

当前状态：已实现但未接入主 Pipeline。
使用方式：python -m src.agents.storyboard_agent.cli --project <id>
"""
from .agent import StoryboardAgent
