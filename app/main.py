"""
AI 小说家 — 服务入口
=====================
分层架构:
  api/      - 路由层（HTTP 请求/响应）
  services/ - 业务逻辑层
  db/       - 数据访问层
  core/     - 核心模块（LLM、Prompt）
"""
import sys, os, socket, threading, webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# ── 前端目录 ──────────────────────────────────────────
BASE = Path(__file__).parent.parent
DIST = BASE / "frontend" / "dist"

if not (DIST / "index.html").exists():
    print("❌ 前端未构建！请运行: cd frontend && npm run build")
    sys.exit(1)

# ── FastAPI App ───────────────────────────────────────
app = FastAPI(title="AI 小说家", version="3.0")
app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")
app.mount("/videos", StaticFiles(directory=str(DIST / "videos")), name="videos")

# ── 注册路由 ──────────────────────────────────────────
from app.api.novels import router as novels_router
from app.api.video import router as video_router
app.include_router(video_router)
app.include_router(novels_router)

# ── 首页 / SPA Fallback ───────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse((DIST / "index.html").read_text(encoding="utf-8"))

@app.get("/{path:path}")
async def spa(path: str):
    if path.startswith("api/"):
        return {"error": "not found"}
    return HTMLResponse((DIST / "index.html").read_text(encoding="utf-8"))


# ── 启动 ──────────────────────────────────────────────
PORT = 8080

def find_port():
    global PORT
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('0.0.0.0', PORT))
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('0.0.0.0', 0))
            PORT = s.getsockname()[1]

def main():
    find_port()
    print(f"""
╔══════════════════════════════════════╗
║     ✍️  AI 小说家 v3.0              ║
║     http://localhost:{PORT:<5}           ║
╚══════════════════════════════════════╝
""")
    threading.Thread(target=lambda: webbrowser.open(f"http://localhost:{PORT}"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
