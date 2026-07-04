"""
Demo: 快速体验完整流水线（Mock 模式）

运行: python examples/demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LLM_API_KEY", "sk-mock-test-key")

from src.pipeline.pipeline import VideoPipeline

# Mock 模式演示（不需要任何 API Key）
pipeline = VideoPipeline(use_mock=True, director_model="gpt-4o")

# 测试创意
ideas = [
    ("一只小猫在霓虹灯下的东京街头寻找回家的路", "anime"),
    ("宇航员在火星上发现了一朵花", "cinematic"),
]

for idea, style in ideas:
    print("\n" + "=" * 60)
    production = pipeline.produce(idea, style=style)
    print(f"进度: {production.progress_report()}")
