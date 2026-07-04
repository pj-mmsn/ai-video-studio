"""
Web 可视化界面后端 — FastAPI + SSE 实时进度推送
============================================================
启动: python -m src.web.app
访问: http://localhost:8000

API:
  GET  /api/models       — 获取可用模型列表
  POST /api/produce      — 开始制作（返回 SSE 流）
  GET  /api/progress     — 查询项目进度
  GET  /api/output       — 输出文件列表
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

# 确保项目根在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from config import config
from src.pipeline.pipeline import VideoPipeline
from src.logging_config import info, error as log_error

app = FastAPI(title="AI Video Studio", version="2.0")

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 输出目录
OUTPUT_DIR = Path(config.output_dir).resolve()


# ================================================================
# 数据模型
# ================================================================

@dataclass
class ModelOption:
    id: str
    name: str
    type: str           # "llm" | "image" | "video"
    base_url: str = ""
    description: str = ""

AVAILABLE_MODELS = {
    "director": [
        ModelOption("deepseek-v4-pro", "DeepSeek V4 Pro", "llm",
                    "https://api.z.ai", "本项目同款，推理能力强，剧本创作首选"),
        ModelOption("deepseek-chat", "DeepSeek V3", "llm",
                    "https://api.deepseek.com/v1", "中文优秀，性价比高"),
        ModelOption("deepseek-reasoner", "DeepSeek R1", "llm",
                    "https://api.deepseek.com/v1", "深度推理，复杂剧情首选"),
        ModelOption("gpt-4o", "GPT-4o", "llm",
                    "https://api.openai.com/v1", "创意最佳，指令遵循好"),
    ],
    "storyboard": [
        ModelOption("mock", "Mock 占位图", "image", "", "免费，Pillow 生成示意分镜"),
        ModelOption("dall-e-3", "DALL-E 3", "image",
                    "https://api.openai.com/v1", "自然语言理解最强"),
    ],
    "videographer": [
        ModelOption("mock", "Mock 静态帧", "video", "", "免费，占位帧"),
        ModelOption("runway-gen3", "RunwayML Gen-3", "video",
                    "", "图生视频质量最高（需 API Key）"),
    ],
}

STYLES = [
    {"id": "cinematic", "name": "电影感", "icon": "🎬", "desc": "写实光影，史诗构图"},
    {"id": "anime", "name": "日式动漫", "icon": "🌸", "desc": "吉卜力/新海诚风格"},
    {"id": "3d", "name": "3D 渲染", "icon": "🧊", "desc": "Pixar 风格，圆润质感"},
    {"id": "watercolor", "name": "水彩画风", "icon": "🎨", "desc": "柔和笔触，诗意画面"},
    {"id": "pixel-art", "name": "像素艺术", "icon": "👾", "desc": "复古游戏风格"},
    {"id": "oil-painting", "name": "油画风格", "icon": "🖼️", "desc": "古典厚重质感"},
]

# 全局：正在运行的任务
running_tasks: dict[str, dict] = {}


# ================================================================
# API 路由
# ================================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页"""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AI Video Studio</h1><p>前端页面未找到，请先构建。</p>")


@app.get("/api/models")
async def get_models():
    return {
        "director": [asdict(m) for m in AVAILABLE_MODELS["director"]],
        "storyboard": [asdict(m) for m in AVAILABLE_MODELS["storyboard"]],
        "videographer": [asdict(m) for m in AVAILABLE_MODELS["videographer"]],
        "styles": STYLES,
    }


@app.post("/api/produce")
async def produce(request: Request):
    """启动制作，返回 SSE 进度流"""
    body = await request.json()
    idea = body.get("idea", "一只猫在太空站冒险")
    style = body.get("style", "cinematic")
    director_model = body.get("director_model", "deepseek-chat")
    storyboard_model = body.get("storyboard_model", "mock")
    videographer_model = body.get("videographer_model", "mock")
    use_mock = body.get("use_mock", True)
    scene_count = body.get("scene_count", 5)
    duration_per_scene = body.get("duration_per_scene", 5)

    # Mock 模式：直接覆盖 config 对象的 api_key（避免 dataclass default_factory 缓存空值）
    if use_mock:
        os.environ["LLM_API_KEY"] = "sk-mock-mode"
        os.environ.setdefault("LLM_BASE_URL", "https://api.openai.com/v1")
        os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
        # 重载 config——因为 config 在模块加载时已经读了空 Key
        from config import config as cfg
        cfg.director.api_key = "sk-mock-mode"
        cfg.storyboard.api_key = "sk-mock-mode"
        cfg.videographer.api_key = "sk-mock-mode"

    task_id = f"task_{int(time.time())}"
    running_tasks[task_id] = {"status": "starting", "progress": 0}

    async def progress_stream():
        """SSE 进度推送"""
        yield f"data: {json.dumps({'type': 'start', 'task_id': task_id, 'message': '开始制作...'})}\n\n"

        try:
            # 创建 Pipeline
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': '初始化 Pipeline...'})}\n\n"

            pipeline = VideoPipeline(
                director_model=director_model if not use_mock else None,
                use_mock=use_mock,
                enable_reviewer=True,
                project_id=task_id,
            )

            # Stage 1
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'script', 'progress': 10, 'message': '🎬 正在生成剧本...'})}\n\n"
            await asyncio.sleep(0.1)

            # Stage 2
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'storyboard', 'progress': 35, 'message': '🎨 正在生成分镜图...'})}\n\n"
            await asyncio.sleep(0.1)

            # Stage 3
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'video', 'progress': 60, 'message': '🎥 正在生成视频片段...'})}\n\n"
            await asyncio.sleep(0.1)

            # 执行
            production = pipeline.produce(idea, style)
            pipeline.close()

            # 结果
            result = {
                "title": production.title,
                "scenes": len(production.script.scenes) if production.script else 0,
                "shots": len(production.storyboard.shots) if production.storyboard else 0,
                "clips": len(production.clips),
                "db_path": str(pipeline.repo.db_path) if pipeline.repo else "",
                "progress_report": production.progress_report(),
            }

            running_tasks[task_id] = {"status": "done", "progress": 100, "result": result}
            yield f"data: {json.dumps({'type': 'done', 'progress': 100, 'result': result})}\n\n"

        except Exception as e:
            log_error(f"制作失败: {e}")
            running_tasks[task_id] = {"status": "failed", "error": str(e)}
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        progress_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    task = running_tasks.get(task_id, {})
    return task


@app.get("/api/output")
async def list_output():
    """列出输出文件"""
    files = []
    for f in OUTPUT_DIR.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".png", ".jpg", ".mp4"):
            files.append({
                "name": f.name,
                "path": str(f.relative_to(OUTPUT_DIR)),
                "size": f.stat().st_size,
                "type": f.suffix,
            })
    return {"files": sorted(files, key=lambda x: x["name"])[:20]}


@app.get("/api/output/{file_path:path}")
async def serve_output(file_path: str):
    """直接访问输出文件"""
    full = OUTPUT_DIR / file_path
    if full.exists():
        return FileResponse(str(full))
    return JSONResponse({"error": "not found"}, status_code=404)


# ================================================================
# 启动
# ================================================================

def main():
    print("🎬 AI Video Studio Web 启动")
    print("   访问: http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
