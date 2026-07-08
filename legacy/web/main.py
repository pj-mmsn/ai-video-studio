"""
AI Video Studio — Web 后端入口
================================
启动: python -m src.web.main
访问: http://localhost:8080
"""
import sys, os, traceback, logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ── 创建 App ──────────────────────────────────────────
app = FastAPI(title="AI Video Studio", version="3.0")

# ── 静态文件 ──────────────────────────────────────────
FRONTEND_DIST = (Path(__file__).parent.parent.parent / "frontend" / "dist").resolve()
FRONTEND_DIST.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


# ── 请求日志中间件 ────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    log.info(f"→ {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            log.warning(f"← {request.method} {request.url.path} → {response.status_code}")
        return response
    except Exception:
        log.error(f"✗ {request.method} {request.url.path}\n{traceback.format_exc()}")
        raise


# ── 异常处理 ──────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    path = request.url.path
    if not path.startswith("/api/"):
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return JSONResponse({"error": "not found", "path": path}, status_code=404)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"未处理异常 {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}")
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": str(exc), "detail": traceback.format_exc()}, status_code=500)
    return HTMLResponse(f"<h1>500 服务器错误</h1><pre>{traceback.format_exc()}</pre>", status_code=500)


# ── 注册 API 路由 ─────────────────────────────────────
from src.web.api.video import router as video_router
from src.web.api.novels import router as novels_router

app.include_router(video_router)
app.include_router(novels_router)


# ── 首页 ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AI Video Studio</h1><p>前端未构建。请运行: cd frontend && npm run build</p>")


# ── 启动 ──────────────────────────────────────────────
def main():
    import socket
    port = 8080
    # 如果 8080 被占用，自动找下一个可用端口
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('0.0.0.0', port))
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('0.0.0.0', 0))
            port = s.getsockname()[1]

    print(f"🎬 AI Video Studio v3.0  端口: {port}")
    print(f"   访问: http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
