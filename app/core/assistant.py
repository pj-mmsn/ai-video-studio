"""
节后分析引擎 — 读完一节正文后，调用 LLM 提取角色/关系/伏笔/世界观
"""
from app.config import load_config
from app.core.llm import chat
from app.core.prompts import ANALYZE_PROMPT
from app.utils import parse_json_response


def analyze_section(repo, node_id: int, content: str) -> dict:
    """分析刚写完的一节，返回解析后的 dict 或空 dict。
    成功时会自动写入数据库。
    """
    if not content or len(content) < 200:
        return {}

    # 获取大纲上下文
    node = repo.conn.execute(
        "SELECT volume_title, chapter_title, section_order, section_title, summary "
        "FROM outline_nodes WHERE id=?", (node_id,)
    ).fetchone()
    if not node:
        return {}

    vt, ct, so, st, summary = node
    outline_ctx = f"卷：{vt}\n章：{ct}\n第{so}节「{st}」\n概要：{summary}"

    cfg = load_config()
    user_prompt = f"【大纲】\n{outline_ctx}\n\n【已写正文】\n{content[:6000]}"

    try:
        raw = chat(cfg, ANALYZE_PROMPT, user_prompt, temperature=0.3)
        parsed, err = parse_json_response(raw)
        if err:
            print(f"  ⚠️ 分析解析失败: {err[:100]}")
            return {}

        # 写入数据库
        section_id = repo.conn.execute(
            "SELECT id FROM sections WHERE outline_node_id=? ORDER BY id DESC LIMIT 1",
            (node_id,)
        ).fetchone()
        if section_id:
            repo.apply_analysis(section_id["id"], parsed)

        summary_parts = []
        if parsed.get("new_characters"):
            summary_parts.append(f"+{len(parsed['new_characters'])}角色")
        if parsed.get("relationships"):
            summary_parts.append(f"+{len(parsed['relationships'])}关系")
        if parsed.get("new_threads"):
            summary_parts.append(f"+{len(parsed['new_threads'])}伏笔")
        if parsed.get("resolved_threads"):
            summary_parts.append(f"✓{len(parsed['resolved_threads'])}回收")
        if parsed.get("world_rules"):
            summary_parts.append(f"+{len(parsed['world_rules'])}规则")
        if summary_parts:
            print(f"  📊 分析完成: {', '.join(summary_parts)}")

        return parsed
    except Exception as e:
        print(f"  ⚠️ 分析调用失败: {e}")
        return {}
