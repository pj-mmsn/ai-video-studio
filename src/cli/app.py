"""
AI 视频工作室 — CLI 入口 + Demo
============================================================
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.pipeline import VideoPipeline
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()

STYLES = {
    "1": ("cinematic", "电影感"),
    "2": ("anime", "日式动漫"),
    "3": ("3d", "3D 渲染"),
    "4": ("watercolor", "水彩画风"),
    "5": ("pixel-art", "像素艺术"),
    "6": ("oil-painting", "油画风格"),
}


def main():
    console.print(Panel.fit(
        "🎬 AI 视频工作室\n"
        "多模型协作：推理模型写剧本 → 图像模型画分镜 → 视频模型制成片",
        title="AI Video Studio",
        border_style="cyan",
    ))

    # 选择风格
    table = Table(title="可选视觉风格")
    table.add_column("编号", style="cyan")
    table.add_column("风格", style="green")
    table.add_column("说明", style="dim")
    for k, (style, desc) in STYLES.items():
        table.add_row(k, style, desc)
    console.print(table)

    style_choice = Prompt.ask("选择风格编号", choices=list(STYLES.keys()), default="1")
    style_name, _ = STYLES[style_choice]

    # 输入想法
    idea = Prompt.ask("\n💡 输入你的视频创意", default="一只猫在太空站冒险")
    use_mock = Prompt.ask("使用 Mock 模式？(无 API Key 时选 y)", choices=["y", "n"], default="y") == "y"

    # 选择剧本模型
    console.print("\n📝 剧本模型选择:")
    console.print("  1. gpt-4o (推荐，创意最佳)")
    console.print("  2. deepseek-chat (性价比)")
    console.print("  3. 自定义")
    model_choice = Prompt.ask("选择", choices=["1", "2", "3"], default="1")
    director_model = {"1": "gpt-4o", "2": "deepseek-chat"}.get(model_choice)
    if model_choice == "3":
        director_model = Prompt.ask("输入模型名")

    # 启动流水线
    pipeline = VideoPipeline(
        director_model=director_model,
        use_mock=use_mock,
    )

    production = pipeline.produce(idea, style=style_name)

    # 输出结果
    console.print("\n" + "=" * 60)
    console.print(Panel.fit(
        f"🎉 制作完成！\n\n"
        f"📝 剧本: {production.script.title if production.script else 'N/A'}\n"
        f"🎨 分镜: {len(production.storyboard.shots) if production.storyboard else 0} 个镜头\n"
        f"🎬 视频: {len(production.clips)} 个片段\n"
        f"📁 输出: {os.path.abspath('output')}",
        title="制作报告",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
