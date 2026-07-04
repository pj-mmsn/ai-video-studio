"""
CLI — 支持交互式和命令行参数两种模式

交互式: python -m src.cli.app
命令行: python -m src.cli.app --idea "猫在太空站" --style anime --output my_video
"""
import argparse
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.pipeline.pipeline import VideoPipeline
from src.logging_config import info, error as log_error


def parse_args():
    p = argparse.ArgumentParser(
        description="🎬 AI 视频工作室 — 多模型协作视频制作",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m src.cli.app --idea "一只猫在太空站冒险" --style anime
  python -m src.cli.app -i "宇航员发现外星花朵" -s cinematic --mock
  python -m src.cli.app --resume my_project_2024
        """
    )
    p.add_argument("-i", "--idea", default=None,
                   help="视频创意（一句话描述）")
    p.add_argument("-s", "--style", default="cinematic",
                   choices=["cinematic", "anime", "3d", "watercolor", "pixel-art", "oil-painting"],
                   help="视觉风格")
    p.add_argument("--mock", action="store_true", default=False,
                   help="Mock 模式（无需 API Key）")
    p.add_argument("--no-review", action="store_true", default=False,
                   help="禁用审查员")
    p.add_argument("--strictness", type=int, default=6,
                   help="审查严格度 (1-10)")
    p.add_argument("--project-id", default=None,
                   help="项目 ID（用于断点续传）")
    p.add_argument("--resume", default=None,
                   help="恢复指定项目 ID 的未完成任务")
    p.add_argument("--director-model", default="gpt-4o",
                   help="剧本模型")
    p.add_argument("-o", "--output", default=None,
                   help="输出目录")
    return p.parse_args()


def run_cli(args):
    """命令行模式"""
    idea = args.idea or "一只小猫在霓虹灯下的东京街头寻找回家的路"
    project_id = args.resume or args.project_id or f"proj_{int(time.time())}"

    info(f"🎬 AI 视频工作室 v2.0")
    info(f"   创意: {idea}")
    info(f"   风格: {args.style}")
    info(f"   项目: {project_id}")
    info(f"   模式: {'Mock' if args.mock else '真实API'} | "
         f"审查: {'关闭' if args.no_review else f'严格度{args.strictness}'}")

    pipeline = VideoPipeline(
        director_model=args.director_model,
        use_mock=args.mock,
        enable_reviewer=not args.no_review,
        reviewer_strictness=args.strictness,
        project_id=project_id,
    )

    try:
        production = pipeline.produce(idea, args.style)
        info(f"\n✅ 制作完成: {production.title}")
        info(f"   进度: {production.progress_report()}")
        info(f"   数据库: {pipeline.repo.db_path}")
    except Exception as e:
        log_error(f"制作失败: {e}")
        raise
    finally:
        pipeline.close()


def run_interactive():
    """交互式模式"""
    from rich.console import Console
    from rich.prompt import Prompt
    console = Console()

    console.print("[bold cyan]🎬 AI 视频工作室 v2.0[/bold cyan]")
    console.print("[dim]多模型协作：推理模型写剧本 → 图像模型画分镜 → 视频模型制成片[/dim]\n")

    idea = Prompt.ask("💡 输入你的视频创意", default="一只猫在太空站冒险")
    style = Prompt.ask("🎨 视觉风格",
                       choices=["cinematic", "anime", "3d", "watercolor", "pixel-art"],
                       default="cinematic")
    use_mock = Prompt.ask("🧪 Mock模式？", choices=["y", "n"], default="y") == "y"

    pipeline = VideoPipeline(use_mock=use_mock)
    try:
        pipeline.produce(idea, style)
    finally:
        pipeline.close()


if __name__ == "__main__":
    args =  parse_args()
    if args.idea or args.resume:
        run_cli(args)
    else:
        run_interactive()
