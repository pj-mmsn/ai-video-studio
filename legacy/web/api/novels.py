"""
小说写作 API
=============
/api/novels/*  构思 / 大纲 / 写作 / 审稿 / 角色 / 导出
/api/config    配置信息
"""
import asyncio, json, datetime, threading, queue
from pathlib import Path

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse, Response

from app.config import load_config
from src.core.prompts import IDEA_PROMPT, OUTLINE_PROMPT, WRITE_PROMPT, REVISE_PROMPT, REVIEW_PROMPT
from src.models.llm_client import chat, chat_stream
from src.db.novel_repository import NovelRepository
from src.desktop.utils import clean_output, parse_json_response, build_full_novel, build_full_html, count_words

router = APIRouter(prefix="/api", tags=["novels"])

NOVELS_DIR = Path("output/novels").resolve()
NOVELS_DIR.mkdir(parents=True, exist_ok=True)


def _get_repo(novel_id: str) -> NovelRepository:
    """获取 NovelRepository"""
    return NovelRepository(novel_id, str(NOVELS_DIR))


# ── 项目管理 ──────────────────────────────────────────
@router.post("/novels")
async def create_novel():
    import uuid
    nid = f"novel_{uuid.uuid4().hex[:8]}"
    repo = _get_repo(nid)
    now = datetime.datetime.now().isoformat()
    repo.conn.execute(
        "INSERT INTO novels (id, title, status, created_at, updated_at) VALUES (?,?,?,?,?)",
        (nid, "", "draft", now, now))
    repo.conn.commit()
    repo.close()
    return {"id": nid, "title": ""}


@router.get("/novels")
async def list_novels():
    import sqlite3
    projects = []
    for d in NOVELS_DIR.iterdir():
        if d.is_dir():
            db_file = d / "novel.db"
            if db_file.exists():
                try:
                    conn = sqlite3.connect(str(db_file))
                    row = conn.execute("SELECT id, title, genre, total_words, status FROM novels LIMIT 1").fetchone()
                    conn.close()
                    if row:
                        projects.append({"id": row[0], "title": row[1] or "未命名", "genre": row[2] or "",
                                         "words": row[3] or 0, "status": row[4] or "draft"})
                except Exception:
                    pass
    projects.sort(key=lambda p: p["id"], reverse=True)
    return projects


@router.get("/novels/{novel_id}")
async def get_novel(novel_id: str):
    repo = _get_repo(novel_id)
    row = repo.conn.execute(
        "SELECT id, title, genre, premise, status, total_words FROM novels WHERE id=?", (novel_id,)).fetchone()
    if not row:
        repo.close()
        return JSONResponse({"error": "not found"}, status_code=404)

    novel = {"id": row[0], "title": row[1] or "", "genre": row[2] or "",
             "premise": row[3] or "", "status": row[4] or "draft", "total_words": row[5] or 0}

    chars = repo.conn.execute("SELECT id, name, role, traits, desire, fear FROM characters WHERE novel_id=?", (novel_id,)).fetchall()
    characters = [{"id": c[0], "name": c[1] or "", "role": c[2] or "",
                   "traits": c[3] or "", "desire": c[4] or "", "fear": c[5] or ""} for c in chars]

    wb = repo.conn.execute(
        "SELECT value FROM story_bible WHERE project_id=? AND category='world_building' LIMIT 1", (novel_id,)).fetchone()
    world_building = wb[0] if wb else ""
    progress = repo.get_progress()
    repo.close()
    return {"novel": novel, "characters": characters, "world_building": world_building, "progress": progress}


# ── 构思 ──────────────────────────────────────────────
@router.post("/novels/{novel_id}/idea")
async def generate_idea(novel_id: str, request: Request):
    body = await request.json()
    idea_text = body.get("idea", "")
    if not idea_text:
        return JSONResponse({"error": "idea is required"}, status_code=400)

    repo = _get_repo(novel_id)
    cfg = load_config()

    async def stream():
        try:
            q = queue.Queue()
            def _run():
                try:
                    chat_stream(cfg, IDEA_PROMPT, f"用户的想法：{idea_text}\n请生成完整小说构思。",
                                on_chunk=lambda t: q.put(("chunk", t)))
                    q.put(("done", None))
                except Exception as e:
                    q.put(("error", str(e)))
            t = threading.Thread(target=_run); t.start()

            full_text = ""
            while True:
                try:
                    kind, data = q.get(timeout=0.1)
                    if kind == "chunk":
                        full_text += data
                        yield f"data: {json.dumps({'type': 'chunk', 'text': data}, ensure_ascii=False)}\n\n"
                    elif kind == "done": break
                    elif kind == "error":
                        yield f"data: {json.dumps({'type': 'error', 'message': data}, ensure_ascii=False)}\n\n"
                        repo.close(); return
                except queue.Empty:
                    await asyncio.sleep(0.05)
            t.join()

            parsed, _ = parse_json_response(full_text)
            if parsed:
                now = datetime.datetime.now().isoformat()
                repo.conn.execute("UPDATE novels SET title=?, genre=?, premise=?, updated_at=? WHERE id=?",
                                  (parsed.get("title", ""), parsed.get("genre", ""), parsed.get("premise", ""), now, novel_id))
                repo.conn.execute("INSERT OR REPLACE INTO story_bible (project_id, category, key, value) VALUES (?,?,?,?)",
                                  (novel_id, "world_building", "main", parsed.get("world_building", "")))
                repo.conn.execute("DELETE FROM characters WHERE novel_id=?", (novel_id,))
                for c in parsed.get("characters", []):
                    repo.conn.execute("INSERT INTO characters (novel_id, name, role, traits, desire, fear) VALUES (?,?,?,?,?,?)",
                                      (novel_id, c.get("name", ""), c.get("role", ""),
                                       c.get("traits", ""), c.get("desire", ""), c.get("fear", "")))
                repo.conn.commit()
                yield f"data: {json.dumps({'type': 'done', 'data': parsed}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'data': {'title': '未命名', 'premise': full_text[:200]}}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            repo.close()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── 大纲 ──────────────────────────────────────────────
@router.get("/novels/{novel_id}/outline")
async def get_outline(novel_id: str):
    repo = _get_repo(novel_id)
    nodes = repo.conn.execute(
        "SELECT id, volume_title, chapter_title, section_order, section_title, summary, status "
        "FROM outline_nodes WHERE novel_id=? ORDER BY sort_order", (novel_id,)).fetchall()
    repo.close()

    tree = []
    for n in nodes:
        nid, vt, ct, so, st, summary, status = n
        if vt and not ct:
            tree.append({"volume_title": vt, "chapters": []})
        elif ct and not st:
            vol = next((v for v in tree if v["volume_title"] == vt), None)
            if vol is None:
                vol = {"volume_title": vt or "", "chapters": []}; tree.append(vol)
            vol["chapters"].append({"chapter_title": ct, "sections": []})
        elif st:
            vol = next((v for v in tree if v["volume_title"] == vt), None)
            if vol is None:
                vol = {"volume_title": vt or "", "chapters": []}; tree.append(vol)
            ch = next((c for c in vol["chapters"] if c["chapter_title"] == ct), None)
            if ch is None:
                ch = {"chapter_title": ct or "", "sections": []}; vol["chapters"].append(ch)
            ch["sections"].append({"id": nid, "section_order": so, "section_title": st or "",
                                   "summary": summary or "", "status": status or "pending"})
    return {"tree": tree}


@router.post("/novels/{novel_id}/outline")
async def generate_outline(novel_id: str, request: Request):
    body = await request.json()
    volumes = body.get("volumes", 3)
    chapters_per_vol = body.get("chapters_per_vol", 4)
    repo = _get_repo(novel_id)
    cfg = load_config()

    row = repo.conn.execute("SELECT title, genre, premise FROM novels WHERE id=?", (novel_id,)).fetchone()
    chars = repo.conn.execute("SELECT name, role FROM characters WHERE novel_id=?", (novel_id,)).fetchall()
    wb = repo.conn.execute("SELECT value FROM story_bible WHERE project_id=? AND category='world_building' LIMIT 1", (novel_id,)).fetchone()

    context = f"故事构思：\n标题：{row[1] if row else ''}\n类型：{row[2] if row else ''}\n梗概：{row[3] if row else ''}\n世界观：{wb[0] if wb else ''}\n角色：{', '.join(f'{c[1]}({c[2]})' for c in chars) if chars else ''}\n\n要求：生成 {volumes} 卷、每卷 {chapters_per_vol} 章的大纲。"

    async def stream():
        try:
            q = queue.Queue()
            def _run():
                try:
                    chat_stream(cfg, OUTLINE_PROMPT, context, on_chunk=lambda t: q.put(("chunk", t)))
                    q.put(("done", None))
                except Exception as e:
                    q.put(("error", str(e)))
            t = threading.Thread(target=_run); t.start()

            full_text = ""
            while True:
                try:
                    kind, data = q.get(timeout=0.1)
                    if kind == "chunk":
                        full_text += data
                        yield f"data: {json.dumps({'type': 'chunk', 'text': data}, ensure_ascii=False)}\n\n"
                    elif kind == "done": break
                    elif kind == "error":
                        yield f"data: {json.dumps({'type': 'error', 'message': data}, ensure_ascii=False)}\n\n"
                        repo.close(); return
                except queue.Empty:
                    await asyncio.sleep(0.05)
            t.join()

            parsed, _ = parse_json_response(full_text)
            if not parsed:
                full_text = chat(cfg, OUTLINE_PROMPT, context)
                parsed, _ = parse_json_response(full_text)

            if parsed and "volumes" in parsed:
                repo.conn.execute("DELETE FROM outline_nodes WHERE novel_id=?", (novel_id,))
                sort = 0
                for vi, vol in enumerate(parsed["volumes"]):
                    vt = vol.get("title", f"第{vi+1}卷")
                    repo.conn.execute("INSERT INTO outline_nodes (novel_id, volume_title, sort_order) VALUES (?,?,?)", (novel_id, vt, sort)); sort += 1
                    for ci, ch in enumerate(vol.get("chapters", [])):
                        ct = ch.get("title", f"第{ci+1}章")
                        repo.conn.execute("INSERT INTO outline_nodes (novel_id, volume_title, chapter_title, summary, sort_order) VALUES (?,?,?,?,?)",
                                          (novel_id, vt, ct, ch.get("summary", ""), sort)); sort += 1
                        for si, sec in enumerate(ch.get("sections", [])):
                            repo.conn.execute("INSERT INTO outline_nodes (novel_id, volume_title, chapter_title, section_order, section_title, summary, sort_order) VALUES (?,?,?,?,?,?,?)",
                                              (novel_id, vt, ct, si+1, sec.get("title", ""), sec.get("summary", ""), sort)); sort += 1
                repo.conn.commit()
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': '大纲解析失败'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            repo.close()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.put("/novels/{novel_id}/outline/{node_id}")
async def update_outline_node(novel_id: str, node_id: int, request: Request):
    body = await request.json()
    repo = _get_repo(novel_id)
    allowed = ["section_title", "summary", "status", "volume_title", "chapter_title"]
    updates = {k: body[k] for k in allowed if k in body}
    if not updates:
        repo.close(); return JSONResponse({"error": "no valid fields"}, status_code=400)
    sets = ", ".join(f"{k}=?" for k in updates)
    repo.conn.execute(f"UPDATE outline_nodes SET {sets} WHERE id=?", list(updates.values()) + [node_id])
    repo.conn.commit(); repo.close()
    return {"ok": True}


@router.delete("/novels/{novel_id}/outline/{node_id}")
async def delete_outline_node(novel_id: str, node_id: int):
    repo = _get_repo(novel_id)
    repo.conn.execute("DELETE FROM outline_nodes WHERE id=?", (node_id,))
    repo.conn.execute("DELETE FROM sections WHERE outline_node_id=?", (node_id,))
    repo.conn.commit(); repo.close()
    return {"ok": True}


@router.post("/novels/{novel_id}/outline/batch-replace")
async def batch_replace_outline(novel_id: str, request: Request):
    body = await request.json()
    find, replace = body.get("find", ""), body.get("replace", "")
    if not find:
        return JSONResponse({"error": "find is required"}, status_code=400)
    repo = _get_repo(novel_id)
    count = 0
    for col in ["section_title", "summary", "volume_title", "chapter_title"]:
        repo.conn.execute(f"UPDATE outline_nodes SET {col}=REPLACE({col},?,?) WHERE novel_id=?", (find, replace, novel_id))
        count += repo.conn.execute("SELECT CHANGES()").fetchone()[0]
    repo.conn.commit(); repo.close()
    return {"count": count}


# ── 写作 ──────────────────────────────────────────────
@router.get("/novels/{novel_id}/sections/{node_id}")
async def get_section(novel_id: str, node_id: int):
    repo = _get_repo(novel_id)
    row = repo.conn.execute(
        "SELECT content FROM sections WHERE novel_id=? AND outline_node_id=? ORDER BY version DESC LIMIT 1",
        (novel_id, node_id)).fetchone()
    repo.close()
    return {"content": row[0] if row else ""}


@router.post("/novels/{novel_id}/write/{node_id}")
async def write_section(novel_id: str, node_id: int, request: Request):
    body = await request.json()
    feedback = body.get("feedback", "")
    repo = _get_repo(novel_id)
    cfg = load_config()

    ctx = repo.get_writing_context(node_id) if hasattr(repo, 'get_writing_context') else {"context_text": ""}
    node = repo.conn.execute(
        "SELECT volume_title, chapter_title, section_order, section_title, summary, status FROM outline_nodes WHERE id=?",
        (node_id,)).fetchone()
    if not node:
        repo.close(); return JSONResponse({"error": "node not found"}, status_code=404)

    vt, ct, so, st, summary, status = node
    existing = repo.conn.execute(
        "SELECT content FROM sections WHERE outline_node_id=? ORDER BY version DESC LIMIT 1", (node_id,)).fetchone()
    existing_content = existing[0] if existing else ""

    chapter_ctx = f"【大纲】\n卷：{vt}\n章：{ct}\n第{so}节「{st}」\n概要：{summary}\n"
    context_text = ctx.get("context_text", "")

    if feedback and existing_content:
        sys_prompt = REVISE_PROMPT
        usr = f"{chapter_ctx}\n【前情提要】\n{context_text[:3000]}\n【原文】\n{existing_content}\n【修改意见】\n{feedback}"
    else:
        sys_prompt = WRITE_PROMPT
        fb_part = f"\n【修改意见】\n{feedback}" if feedback else ""
        usr = f"{chapter_ctx}\n【前情提要】\n{context_text[:3000]}{fb_part}"

    async def stream():
        try:
            q = queue.Queue()
            def _run():
                try:
                    chat_stream(cfg, sys_prompt, usr, on_chunk=lambda t: q.put(("chunk", t)))
                    q.put(("done", None))
                except Exception as e:
                    q.put(("error", str(e)))
            t = threading.Thread(target=_run); t.start()

            full_text = ""
            while True:
                try:
                    kind, data = q.get(timeout=0.1)
                    if kind == "chunk":
                        full_text += data
                        yield f"data: {json.dumps({'type': 'chunk', 'text': data}, ensure_ascii=False)}\n\n"
                    elif kind == "done": break
                    elif kind == "error":
                        yield f"data: {json.dumps({'type': 'error', 'message': data}, ensure_ascii=False)}\n\n"
                        repo.close(); return
                except queue.Empty:
                    await asyncio.sleep(0.05)
            t.join()

            body_text = clean_output(full_text)
            summary_line = ""
            if "【本节摘要】" in body_text:
                parts = body_text.split("【本节摘要】")
                body_text = parts[0].strip()
                summary_line = parts[1].strip() if len(parts) > 1 else ""

            wc = count_words(body_text)
            now = datetime.datetime.now().isoformat()
            repo.conn.execute(
                "INSERT INTO sections (novel_id, outline_node_id, content, word_count, summary, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (novel_id, node_id, body_text, wc, summary_line, now, now))
            repo.conn.execute("UPDATE outline_nodes SET status='done' WHERE id=?", (node_id,))
            repo.conn.execute(
                "UPDATE novels SET total_words=(SELECT COALESCE(SUM(word_count),0) FROM sections WHERE novel_id=?), updated_at=? WHERE id=?",
                (novel_id, now, novel_id))
            repo.conn.commit()
            yield f"data: {json.dumps({'type': 'done', 'content': body_text}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            repo.close()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── 审稿 ──────────────────────────────────────────────
@router.post("/novels/{novel_id}/review")
async def review_novel(novel_id: str, request: Request = None):
    repo = _get_repo(novel_id)
    cfg = load_config()

    nodes = repo.conn.execute(
        "SELECT volume_title, chapter_title, section_order, section_title, summary, status FROM outline_nodes WHERE novel_id=? ORDER BY sort_order",
        (novel_id,)).fetchall()
    outline_lines = ["【大纲】"]
    for n in nodes:
        vt, ct, so, st, summary, status = n
        if st:
            mark = "✓" if status == "done" else "○"
            outline_lines.append(f"{mark} {vt} > {ct} > 第{so}节「{st}」: {summary}")
    full_text = build_full_novel(repo)
    usr = "\n".join(outline_lines) + "\n\n【正文】\n" + full_text[:8000]

    async def stream():
        try:
            q = queue.Queue()
            def _run():
                try:
                    chat_stream(cfg, REVIEW_PROMPT, usr, on_chunk=lambda t: q.put(("chunk", t)))
                    q.put(("done", None))
                except Exception as e:
                    q.put(("error", str(e)))
            t = threading.Thread(target=_run); t.start()

            full_text = ""
            while True:
                try:
                    kind, data = q.get(timeout=0.1)
                    if kind == "chunk":
                        full_text += data
                        yield f"data: {json.dumps({'type': 'chunk', 'text': data}, ensure_ascii=False)}\n\n"
                    elif kind == "done": break
                    elif kind == "error":
                        yield f"data: {json.dumps({'type': 'error', 'message': data}, ensure_ascii=False)}\n\n"
                        repo.close(); return
                except queue.Empty:
                    await asyncio.sleep(0.05)
            t.join()

            now = datetime.datetime.now().isoformat()
            try:
                repo.conn.execute("INSERT INTO reviews (novel_id, content, created_at) VALUES (?,?,?)", (novel_id, full_text, now))
                repo.conn.commit()
            except Exception:
                pass
            yield f"data: {json.dumps({'type': 'done', 'content': full_text}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            repo.close()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/novels/{novel_id}/review")
async def get_review(novel_id: str):
    repo = _get_repo(novel_id)
    row = repo.conn.execute("SELECT content FROM reviews WHERE novel_id=? ORDER BY created_at DESC LIMIT 1", (novel_id,)).fetchone()
    repo.close()
    return {"content": row[0] if row else ""}


# ── 角色 ──────────────────────────────────────────────
@router.get("/novels/{novel_id}/characters")
async def list_characters(novel_id: str):
    repo = _get_repo(novel_id)
    chars = repo.conn.execute("SELECT id, name, role, traits, desire, fear FROM characters WHERE novel_id=?", (novel_id,)).fetchall()
    repo.close()
    return {"characters": [{"id": c[0], "name": c[1] or "", "role": c[2] or "",
                            "traits": c[3] or "", "desire": c[4] or "", "fear": c[5] or ""} for c in chars]}

@router.post("/novels/{novel_id}/characters")
async def add_character(novel_id: str, request: Request):
    body = await request.json()
    repo = _get_repo(novel_id)
    repo.conn.execute("INSERT INTO characters (novel_id, name, role, traits, desire, fear) VALUES (?,?,?,?,?,?)",
                      (novel_id, body.get("name", ""), body.get("role", ""),
                       body.get("traits", ""), body.get("desire", ""), body.get("fear", "")))
    repo.conn.commit(); repo.close()
    return {"ok": True}

@router.put("/novels/{novel_id}/characters/{char_id}")
async def update_character(novel_id: str, char_id: int, request: Request):
    body = await request.json()
    repo = _get_repo(novel_id)
    repo.conn.execute("UPDATE characters SET name=?, role=?, traits=?, desire=?, fear=? WHERE id=? AND novel_id=?",
                      (body.get("name", ""), body.get("role", ""), body.get("traits", ""),
                       body.get("desire", ""), body.get("fear", ""), char_id, novel_id))
    repo.conn.commit(); repo.close()
    return {"ok": True}

@router.delete("/novels/{novel_id}/characters/{char_id}")
async def delete_character(novel_id: str, char_id: int):
    repo = _get_repo(novel_id)
    repo.conn.execute("DELETE FROM characters WHERE id=? AND novel_id=?", (char_id, novel_id))
    repo.conn.commit(); repo.close()
    return {"ok": True}


# ── 导出 ──────────────────────────────────────────────
@router.get("/novels/{novel_id}/export")
async def export_novel(novel_id: str, format: str = "txt"):
    repo = _get_repo(novel_id)
    if format == "html":
        content = build_full_html(repo); media = "text/html"; ext = "html"
    else:
        content = build_full_novel(repo); media = "text/plain; charset=utf-8"; ext = "txt"

    title = "novel"
    row = repo.conn.execute("SELECT title FROM novels WHERE id=?", (novel_id,)).fetchone()
    if row and row[0]: title = row[0]
    repo.close()
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename={title}.{ext}"})


@router.get("/novels/{novel_id}/fulltext")
async def get_fulltext(novel_id: str):
    repo = _get_repo(novel_id)
    text = build_full_novel(repo)
    repo.close()
    return {"text": text}


# ── 配置 ──────────────────────────────────────────────
@router.get("/config")
async def get_config():
    from src.web.api.video import AVAILABLE_MODELS, STYLES
    from dataclasses import asdict
    return {
        "models": {
            "director": [asdict(m) for m in AVAILABLE_MODELS["director"]],
            "storyboard": [asdict(m) for m in AVAILABLE_MODELS["storyboard"]],
            "videographer": [asdict(m) for m in AVAILABLE_MODELS["videographer"]],
        },
        "styles": STYLES,
        "current_model": load_config().get("model", "deepseek-v4-pro"),
    }
