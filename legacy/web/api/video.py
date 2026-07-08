"""
视频管线 API
=============
/api/models  /api/produce  /api/progress  /api/output
"""
import asyncio, json, os, time
from pathlib import Path
from dataclasses import dataclass, asdict

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

router = APIRouter(prefix="/api", tags=["video"])

OUTPUT_DIR = Path("output").resolve()

# ── 数据模型 ──────────────────────────────────────────
@dataclass
class ModelOption:
    id: str
    name: str
    type: str
    base_url: str = ""
    description: str = ""

AVAILABLE_MODELS = {
    "director": [
        ModelOption("deepseek-v4-pro", "DeepSeek V4 Pro", "llm", "https://api.z.ai", "推理能力强，剧本创作首选"),
        ModelOption("deepseek-chat", "DeepSeek V3", "llm", "https://api.deepseek.com/v1", "中文优秀，性价比高"),
        ModelOption("deepseek-reasoner", "DeepSeek R1", "llm", "https://api.deepseek.com/v1", "深度推理，复杂剧情首选"),
        ModelOption("gpt-4o", "GPT-4o", "llm", "https://api.openai.com/v1", "创意最佳，指令遵循好"),
    ],
    "storyboard": [
        ModelOption("mock", "Mock 占位图", "image", "", "免费，Pillow 生成示意分镜"),
        ModelOption("dall-e-3", "DALL-E 3", "image", "https://api.openai.com/v1", "自然语言理解最强"),
    ],
    "videographer": [
        ModelOption("mock", "Mock 静态帧", "video", "", "免费，占位帧"),
        ModelOption("runway-gen3", "RunwayML Gen-3", "video", "", "图生视频质量最高（需 API Key）"),
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

running_tasks: dict[str, dict] = {}


# ── 路由 ──────────────────────────────────────────────
@router.get("/models")
async def get_models():
    from src.web.api.novels import get_config  # 复用 novels 模块的配置接口
    return {
        "director": [asdict(m) for m in AVAILABLE_MODELS["director"]],
        "storyboard": [asdict(m) for m in AVAILABLE_MODELS["storyboard"]],
        "videographer": [asdict(m) for m in AVAILABLE_MODELS["videographer"]],
        "styles": STYLES,
    }


@router.post("/produce")
async def produce(request: Request):
    """启动视频制作，返回 SSE 进度流"""
    body = await request.json()
    idea = body.get("idea", "一只猫在太空站冒险")
    style = body.get("style", "cinematic")
    director_model = body.get("director_model", "deepseek-chat")
    use_mock = body.get("use_mock", True)

    if use_mock:
        os.environ["LLM_API_KEY"] = "sk-mock-mode"
        from app.config import load_config, reload_config
        reload_config()

    task_id = f"task_{int(time.time())}"
    running_tasks[task_id] = {"status": "starting", "progress": 0}

    async def progress_stream():
        yield f"data: {json.dumps({'type': 'start', 'task_id': task_id, 'message': '开始制作...'})}\n\n"

        try:
            from src.pipeline.pipeline import VideoPipeline

            yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': '初始化 Pipeline...'})}\n\n"
            pipeline = VideoPipeline(
                director_model=director_model if not use_mock else None,
                use_mock=use_mock,
                enable_reviewer=True,
                project_id=task_id,
            )

            yield f"data: {json.dumps({'type': 'progress', 'stage': 'script', 'progress': 10, 'message': '🎬 正在生成剧本...'})}\n\n"
            await asyncio.sleep(0.1)

            yield f"data: {json.dumps({'type': 'progress', 'stage': 'storyboard', 'progress': 35, 'message': '🎨 正在生成分镜图...'})}\n\n"
            await asyncio.sleep(0.1)

            yield f"data: {json.dumps({'type': 'progress', 'stage': 'video', 'progress': 60, 'message': '🎥 正在生成视频片段...'})}\n\n"
            await asyncio.sleep(0.1)

            production = pipeline.produce(idea, style)
            pipeline.close()

            result = {
                "title": production.title,
                "scenes": len(production.script.scenes) if production.script else 0,
                "shots": len(production.storyboard.shots) if production.storyboard else 0,
                "clips": len(production.clips),
                "progress_report": production.progress_report(),
            }

            running_tasks[task_id] = {"status": "done", "progress": 100, "result": result}
            yield f"data: {json.dumps({'type': 'done', 'progress': 100, 'result': result})}\n\n"

        except Exception as e:
            running_tasks[task_id] = {"status": "failed", "error": str(e)}
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        progress_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    return running_tasks.get(task_id, {})


@router.get("/output")
async def list_output():
    files = []
    for f in OUTPUT_DIR.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".png", ".jpg", ".mp4"):
            files.append({
                "name": f.name, "path": str(f.relative_to(OUTPUT_DIR)),
                "size": f.stat().st_size, "type": f.suffix,
            })
    return {"files": sorted(files, key=lambda x: x["name"])[:20]}


@router.get("/output/{file_path:path}")
async def serve_output(file_path: str):
    full = OUTPUT_DIR / file_path
    if full.exists():
        return FileResponse(str(full))
    return JSONResponse({"error": "not found"}, status_code=404)
