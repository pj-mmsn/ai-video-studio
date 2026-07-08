"""
小说家桌面应用 — PyWebView 原生窗口 + Web 实时监控
============================================================
启动: python -m src.desktop.novelist

依赖: pip install pywebview
- Windows: 使用 Edge WebView2（系统自带）
- Mac: 使用 WebKit（系统自带）
- Linux: 需要安装 webkit2gtk

如果 pywebview 不可用，自动降级为浏览器模式。
"""
import sys
import os
import json
import threading
import queue

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from src.db.novel_repository import NovelRepository
from src.agents.novelist import NovelistAgent
from src.models import LLMClient
from src.logging_config import info

app = FastAPI(title="小说家桌面版")
static = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static, exist_ok=True)
app.mount("/static", StaticFiles(directory=static), name="static")

# 当前会话
current_session = {"agent": None, "repo": None, "streaming": False, "pause": False}
output_queue = queue.Queue()


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(static, "novelist.html")
    if os.path.exists(html_path):
        return HTMLResponse(open(html_path, encoding="utf-8").read())
    return HTMLResponse("<h1>页面未找到</h1>")


@app.post("/api/init")
async def init_novel(request: Request):
    body = await request.json()
    idea = body.get("idea", "")
    genre = body.get("genre", "玄幻")

    repo = NovelRepository(f"novel_{int(__import__('time').time())}")
    agent = NovelistAgent(LLMClient())

    # 初始化小说框架
    novel = agent.init_novel(idea, genre)

    # 保存到数据库
    repo.conn.execute(
        "INSERT INTO novels (id,title,genre,premise,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
        (repo.novel_id, novel.title, genre, novel.premise, "draft",
         __import__('datetime').datetime.now().isoformat(),
         __import__('datetime').datetime.now().isoformat())
    )

    # 创建三层大纲: 卷→章→节
    volume_count = 3
    chapters_per_volume = 5
    sections_per_chapter = 4
    sort = 0
    parent_map = {}  # {volume_idx: node_id}

    for v in range(1, volume_count + 1):
        repo.conn.execute(
            "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
            (repo.novel_id, None, "volume", sort, f"第{v}卷",
             novel.outline[v-1] if v <= len(novel.outline) else f"第{v}卷内容", "pending")
        )
        vid = repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        sort += 1

        for c in range(1, chapters_per_volume + 1):
            repo.conn.execute(
                "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                (repo.novel_id, vid, "chapter", sort, f"第{v}卷第{c}章", "", "pending")
            )
            cid = repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            sort += 1

            for s in range(1, sections_per_chapter + 1):
                repo.conn.execute(
                    "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                    (repo.novel_id, cid, "section", sort, f"第{v}卷第{c}章第{s}节", "", "pending")
                )
                sort += 1
    repo.conn.commit()

    # 保存角色
    for c in novel.characters:
        repo.conn.execute(
            "INSERT INTO characters (novel_id,name,role,traits,arc,updated_at) VALUES (?,?,?,?,?,?)",
            (repo.novel_id, c.name, c.role, c.description, "",
             __import__('datetime').datetime.now().isoformat())
        )
    repo.conn.commit()

    current_session["repo"] = repo
    current_session["agent"] = agent

    # 返回大纲树
    outline = repo.get_outline_tree()
    return {"novel_id": repo.novel_id, "title": novel.title, "outline": outline}


@app.get("/api/write/{node_id}")
async def write_section(node_id: int):
    """开始写一节——流式返回内容"""
    from fastapi.responses import StreamingResponse

    async def stream():
        repo = current_session["repo"]
        if not repo:
            yield f"data: {json.dumps({'error': '请先初始化小说'})}\n\n"
            return

        # 获取上下文
        ctx = repo.get_writing_context(node_id)
        context_text = ctx["context_text"]
        token_est = ctx["token_estimate"]
        node = repo.get_node(node_id)

        yield f"data: {json.dumps({'type': 'context', 'text': context_text, 'tokens': token_est})}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'msg': f'开始写 {node[\"title\"]}...'})}\n\n"

        # 写作
        agent = current_session["agent"]
        if agent:
            agent.novel.outline = [node.get("summary", "")]

            # 用 agent 写
            import re
            prompt = f"""请根据大纲写这一节内容。

{context_text}

---
大纲指引: {node['title']}: {node.get('summary','自由发挥')}
要求: 1000-3000字，保持角色和世界观一致。
写完后附上:
【角色提取】: 本节新出场/有变化的角色(JSON格式)
【伏笔提取】: 本节新埋或推进的伏笔(JSON格式)
【规则提取】: 本节新揭示的世界观规则(JSON格式)
【本节摘要】: 2-3句话总结
"""

            raw_text = agent.llm.chat(
                """你是一位职业小说家。请根据大纲和上下文写这一节内容。
保持角色性格一致，逻辑自洽。""",
                prompt
            )

            # 逐段流式输出
            for paragraph in raw_text.split("\n\n"):
                if current_session.get("pause"):
                    break
                if paragraph.strip():
                    yield f"data: {json.dumps({'type': 'content', 'text': paragraph + '\n\n'})}\n\n"
                    import asyncio
                    await asyncio.sleep(0.05)

            # 保存到数据库
            summary_match = re.search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)', raw_text)
            summary = summary_match.group(1) if summary_match else ""
            repo.save_section(node_id, raw_text, summary)

            # 进度
            progress = repo.get_progress()
            yield f"data: {json.dumps({'type': 'done', 'progress': progress})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/pause")
async def toggle_pause():
    current_session["pause"] = not current_session.get("pause", False)
    return {"paused": current_session["pause"]}


@app.get("/api/progress")
async def progress():
    repo = current_session.get("repo")
    if repo:
        return repo.get_progress()
    return {}


def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8200, log_level="warning")


def main():
    # 启动后端服务器（后台线程）
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    import time; time.sleep(1)  # 等服务器就绪

    # 尝试原生窗口
    try:
        import webview
        info("启动桌面窗口...")
        webview.create_window(
            "📖 AI 小说家",
            "http://127.0.0.1:8200",
            width=1400, height=900,
            min_size=(1000, 600),
        )
        webview.start()
    except ImportError:
        import webbrowser
        info("PyWebView 未安装，使用浏览器模式")
        info("访问: http://127.0.0.1:8200")
        webbrowser.open("http://127.0.0.1:8200")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            info("退出")


if __name__ == "__main__":
    main()
