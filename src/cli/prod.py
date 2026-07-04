"""
生产级视频制作 CLI
============================================================
子命令:
  pipeline  - 完整流水线（剧本→分镜→视频→合成）
  script    - 仅生成剧本
  storyboard- 仅生成分镜图
  video     - 生成视频片段
  compose   - 合成最终视频（图片→MP4）
  status    - 查看项目进度
  resume    - 断点续传

示例:
  python -m src.cli.prod pipeline --idea "猫在太空站" --style anime
  python -m src.cli.prod compose --project proj_123 --transition fade --music bgm.mp3
  python -m src.cli.prod video --api runway --image scene_01.png --prompt "camera panning"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.pipeline.pipeline import VideoPipeline
from src.logging_config import info, error as log_error


def build_parser():
    p = argparse.ArgumentParser(
        prog="ai-video",
        description="🎬 AI Video Studio — 生产级视频制作 CLI",
    )
    sub = p.add_subparsers(dest="command", help="子命令")

    # ---- pipeline ----
    pp = sub.add_parser("pipeline", help="完整流水线：剧本→分镜→视频→合成")
    pp.add_argument("--idea", "-i", required=True, help="视频创意")
    pp.add_argument("--style", "-s", default="cinematic",
                    choices=["cinematic","anime","3d","watercolor","pixel-art","oil-painting"])
    pp.add_argument("--director-model", default="deepseek-v4-pro", help="剧本模型")
    pp.add_argument("--image-api", default="mock", choices=["mock","dalle","comfyui"],
                    help="图像生成后端: mock/dalle/comfyui")
    pp.add_argument("--video-api", default="mock", choices=["mock","runway","pika","comfyui"],
                    help="视频生成后端: mock/runway/pika/comfyui")
    pp.add_argument("--scenes", type=int, default=5, help="场景数量 (3-12)")
    pp.add_argument("--duration", type=int, default=5, help="每场景时长(秒)")
    pp.add_argument("--mock", action="store_true", help="Mock模式(无需API Key)")
    pp.add_argument("--no-review", action="store_true", help="跳过审查")
    pp.add_argument("--strictness", type=int, default=6, help="审查严格度 1-10")
    pp.add_argument("--project-id", default=None, help="项目ID(断点续传)")
    pp.add_argument("--output", "-o", default=None, help="输出视频路径")

    # ---- script ----
    sp = sub.add_parser("script", help="仅生成剧本")
    sp.add_argument("--idea", "-i", required=True)
    sp.add_argument("--style", "-s", default="cinematic")
    sp.add_argument("--model", default="deepseek-v4-pro")
    sp.add_argument("--output", "-o", default=None, help="保存JSON路径")

    # ---- storyboard ----
    bp = sub.add_parser("storyboard", help="仅生成分镜图")
    bp.add_argument("--script", required=True, help="剧本JSON路径")
    bp.add_argument("--api", default="mock", choices=["mock","dalle","comfyui"])
    bp.add_argument("--output-dir", default="output/storyboard")

    # ---- video ----
    vp = sub.add_parser("video", help="生成视频片段")
    vp.add_argument("--image", required=True, help="输入图片路径")
    vp.add_argument("--prompt", required=True, help="动效提示词")
    vp.add_argument("--api", default="mock", choices=["mock","runway","pika","comfyui"])
    vp.add_argument("--duration", type=int, default=5)
    vp.add_argument("--output", "-o", default=None)

    # ---- compose ----
    cp = sub.add_parser("compose", help="合成最终视频")
    cp.add_argument("--project", "-p", required=True, help="项目ID")
    cp.add_argument("--transition", default="fade", choices=["fade","slide","zoom","none"])
    cp.add_argument("--music", default=None, help="背景音乐路径")
    cp.add_argument("--subtitles", action="store_true", help="叠加硬字幕")
    cp.add_argument("--watermark", default=None, help="水印文字")
    cp.add_argument("--fps", type=int, default=24)
    cp.add_argument("--output", "-o", default=None)

    # ---- status / resume ----
    st = sub.add_parser("status", help="查看项目进度")
    st.add_argument("--project", "-p", required=True, help="项目ID")

    rp = sub.add_parser("resume", help="断点续传")
    rp.add_argument("--project", "-p", required=True, help="项目ID")

    return p


def cmd_pipeline(args):
    info(f"🎬 启动完整流水线")
    info(f"   创意: {args.idea}")
    info(f"   风格: {args.style}")
    info(f"   导演: {args.director_model} | 图像: {args.image_api} | 视频: {args.video_api}")

    pipeline = VideoPipeline(
        director_model=args.director_model,
        use_mock=args.mock or args.image_api == "mock",
        enable_reviewer=not args.no_review,
        reviewer_strictness=args.strictness,
        project_id=args.project_id,
    )

    try:
        prod = pipeline.produce(args.idea, args.style)
        info(f"\n✅ 完成: {prod.title}")
        info(f"   {prod.progress_report()}")

        # 自动合成 Stage 4
        if prod.storyboard and prod.storyboard.shots:
            from src.tools.composer import VideoComposer
            output_path = args.output or f"output/video/{prod.title.replace(' ', '_')}.mp4"
            composer = VideoComposer(fps=24)
            video_path = composer.compose(prod.storyboard, output_path=output_path, add_subtitles=True)
            if video_path:
                info(f"🎬 最终视频: {video_path}")
    finally:
        pipeline.close()


def cmd_script(args):
    from src.agents.director import DirectorAgent
    from src.models import LLMClient

    director = DirectorAgent(LLMClient(model=args.model))
    script = director.create_script(args.idea, args.style)

    import json
    output = args.output or f"output/scripts/{script.title.replace(' ', '_')}.json"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    data = {"title": script.title, "logline": script.logline, "scenes": [
        {"id": s.scene_id, "desc": s.description, "visual": s.visual_prompt,
         "motion": s.motion_prompt, "camera": s.camera, "dialogue": s.dialogue}
        for s in script.scenes
    ]}
    Path(output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    info(f"✅ 剧本已保存: {output}")


def cmd_storyboard(args):
    from src.agents.storyboard import StoryboardAgent
    from src.models import ImageGenClient, Script, Scene
    import json

    script_data = json.loads(Path(args.script).read_text(encoding="utf-8"))
    scenes = [Scene(
        scene_id=s["id"], description=s["desc"], visual_prompt=s["visual"],
        motion_prompt=s["motion"], camera=s.get("camera",""), dialogue=s.get("dialogue",""),
    ) for s in script_data["scenes"]]

    script = Script(title=script_data["title"], logline=script_data.get("logline",""), scenes=scenes)
    agent = StoryboardAgent(ImageGenClient())
    agent.use_mock = (args.api == "mock")
    storyboard = agent.create_storyboard(script)
    info(f"✅ 分镜完成: {len(storyboard.shots)} 个镜头")


def cmd_video(args):
    from src.agents.videographer import VideographerAgent
    from src.models import VideoGenClient, Shot, Storyboard

    shot = Shot(scene_id=1, image_prompt="", motion_prompt=args.prompt, image_path=args.image)
    storyboard = Storyboard(script_title="single_shot", shots=[shot])

    agent = VideographerAgent(VideoGenClient())
    agent.use_mock = (args.api == "mock")

    if args.api == "runway":
        info("📡 调用 RunwayML API...")
        # agent.client.generate = runway_generate  # TODO: 接入Runway

    clips = agent.produce(storyboard)
    info(f"✅ 视频生成: {len(clips)} 个片段")


def cmd_compose(args):
    from src.tools.composer import VideoComposer
    from src.db.repository import ProjectRepository
    from src.models import Storyboard, Shot

    repo = ProjectRepository(args.project)
    progress = repo.get_progress()

    if not progress["can_resume"]:
        log_error(f"项目 {args.project} 不存在")
        return

    # 从DB恢复分镜数据
    shots_data = repo.get_shots()
    shots = [Shot(
        scene_id=s.scene_id, image_prompt=s.image_prompt,
        motion_prompt=s.motion_prompt, image_path=s.image_path,
    ) for s in shots_data]

    storyboard = Storyboard(script_title=progress["project"].title, shots=shots)

    output = args.output or f"output/video/{args.project}.mp4"
    composer = VideoComposer(fps=args.fps)
    path = composer.compose(storyboard, output_path=output, add_subtitles=args.subtitles)

    if path:
        info(f"🎬 视频已合成: {path}")
        info(f"   转场: {args.transition} | FPS: {args.fps}")
        if args.music:
            info(f"   音乐: {args.music} (需手动用 ffmpeg 叠加)")
    repo.close()


def cmd_status(args):
    from src.db.repository import ProjectRepository
    repo = ProjectRepository(args.project)
    progress = repo.get_progress()
    if not progress["can_resume"]:
        info(f"项目 {args.project} 不存在")
    else:
        info(f"项目: {args.project}")
        info(f"  标题: {progress['project'].title}")
        info(f"  风格: {progress['project'].style}")
        info(f"  进度: {progress['last_stage']}")
        info(f"  场景: {progress['scenes_done']}/{progress['total_scenes']}")
        info(f"  分镜: {progress['shots_done']} | 视频: {progress['clips_done']}")
        info(f"  审查: {progress['reviews_count']} 次")
    repo.close()


def cmd_resume(args):
    args.project_id = args.project
    args.idea = ""
    args.style = "cinematic"
    cmd_pipeline(args)


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "pipeline": cmd_pipeline,
        "script": cmd_script,
        "storyboard": cmd_storyboard,
        "video": cmd_video,
        "compose": cmd_compose,
        "status": cmd_status,
        "resume": cmd_resume,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        log_error(f"执行失败: {e}")
        raise


if __name__ == "__main__":
    main()
