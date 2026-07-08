"""
AI 小说家 — 工具函数
=====================
文本清洗、JSON 解析、字数统计等纯函数。
"""
import json
import re


def clean_output(text: str) -> str:
    """清洗 LLM 输出，去掉 JSON/大纲/标记等非正文内容。

    策略：找到第一个"像小说正文"的段落作为起点。
    判断标准：连续中文字符 >= 15 个，且不含 JSON 特征（引号+冒号）。
    """
    if not text or not text.strip():
        return ""

    paragraphs = text.split('\n')
    start_idx = 0

    for i, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped:
            continue

        # 跳过明显不是正文的行
        if _is_meta_line(stripped):
            continue

        # 检查是否像正文：连续中文字符 >= 15
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', stripped)
        if len(chinese_chars) >= 15:
            start_idx = i
            break

    # 如果没找到正文起点，回退到第一个非标记行
    if start_idx == 0:
        for i, para in enumerate(paragraphs):
            stripped = para.strip()
            if stripped and not _is_meta_line(stripped):
                start_idx = i
                break

    result = '\n'.join(paragraphs[start_idx:]).strip()
    return result


def _is_meta_line(line: str) -> bool:
    """判断一行是否为元信息（JSON 片段、大纲标记等），而非正文"""
    s = line.strip()
    if not s:
        return True

    # JSON 特征
    if s[0] in '{[}]' or (s[0] == '"' and ':' in s):
        return True

    # Markdown 标记
    if s.startswith('```') or s.startswith('---') or s.startswith('***'):
        return True

    # 章节标题标记
    if s.startswith('## ') or s.startswith('# '):
        return True

    # 中文大纲标记："第X卷"、"第X章"、"第X节"
    if re.match(r'^第[一二三四五六七八九十\d]+[卷章节]', s):
        return True

    # JSON key-value 残留
    if re.match(r'^"[a-zA-Z_]+":', s):
        return True

    return False


def parse_json_response(raw: str) -> tuple[dict, str]:
    """从 LLM 返回中解析 JSON。

    Returns:
        (parsed_dict, error_message)
        - 成功时 error_message 为空字符串
        - 失败时 parsed_dict 为空 dict，error_message 包含错误信息
    """
    if not raw or not raw.strip():
        return {}, "LLM 返回为空"

    s = raw.strip()

    # 提取 JSON 块
    if "```json" in s:
        s = s.split("```json")[1].split("```")[0].strip()
    elif "```" in s:
        s = s.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(s), ""
    except json.JSONDecodeError as e:
        # 提供诊断信息
        preview = raw[:300].replace('\n', '\\n')
        return {}, f"JSON 解析失败: {e}\n\n返回内容预览:\n{preview}..."


def count_chinese_chars(text: str) -> int:
    """统计中文字符数（不含标点和空格）"""
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def count_words(text: str) -> int:
    """统计总字符数（中文字符 + 英文单词）"""
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    # 英文单词
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese + english_words


def build_full_novel(repo) -> str:
    """从数据库拼接完整小说文本（使用新平铺列）。"""
    if not repo:
        return ""

    rows = repo.conn.execute(
        "SELECT o.volume_title, o.chapter_title, o.section_order, o.section_title, "
        "o.summary, o.status, "
        "(SELECT s.content FROM sections s WHERE s.outline_node_id = o.id ORDER BY s.id DESC LIMIT 1) as content, "
        "(SELECT s.word_count FROM sections s WHERE s.outline_node_id = o.id ORDER BY s.id DESC LIMIT 1) as word_count "
        "FROM outline_nodes o "
        "WHERE o.novel_id=? AND o.section_title != '' "
        "ORDER BY o.sort_order",
        (repo.novel_id,)
    ).fetchall()

    if not rows:
        return ""

    lines = []
    novel_info = repo.conn.execute(
        "SELECT title, genre, premise FROM novels WHERE id=?",
        (repo.novel_id,)
    ).fetchone()
    if novel_info:
        lines.append(f"《{novel_info['title']}》")
        if novel_info["genre"]:
            lines.append(f"类型：{novel_info['genre']}")
        if novel_info["premise"]:
            lines.append(f"\n{novel_info['premise']}")
        lines.append("\n" + "=" * 50 + "\n")

    last_vol = None
    last_ch = None

    for r in rows:
        # 卷标题
        if r["volume_title"] != last_vol:
            last_vol = r["volume_title"]
            last_ch = None
            lines.append("")
            lines.append(f"╔══ {last_vol} ══╗")
            lines.append("")

        # 章标题
        if r["chapter_title"] != last_ch:
            last_ch = r["chapter_title"]
            lines.append(f"  ■ {last_ch}")
            lines.append("")

        # 正文（不显示节标题，直接连在一起更流畅）
        if r["content"]:
            lines.append(r["content"])
            lines.append("")

    return '\n'.join(lines)


def build_full_html(repo) -> str:
    """从数据库拼接完整小说的 HTML 版本（使用新平铺列）。"""
    novel_info = repo.conn.execute(
        "SELECT title, genre, premise FROM novels WHERE id=?",
        (repo.novel_id,)
    ).fetchone()
    if not novel_info:
        return "<html><body><p>无内容</p></body></html>"

    title = novel_info["title"] or "未命名"
    genre = novel_info["genre"] or ""
    premise = novel_info["premise"] or ""

    rows = repo.conn.execute(
        "SELECT volume_title, chapter_title, section_order, section_title, summary, "
        "COALESCE((SELECT content FROM sections WHERE outline_node_id=o.id ORDER BY id DESC LIMIT 1), '') as content "
        "FROM outline_nodes o "
        "WHERE o.novel_id=? AND o.section_title != '' "
        "ORDER BY o.volume_title, o.chapter_title, o.section_order",
        (repo.novel_id,)
    ).fetchall()

    toc_items = []
    body_parts = []
    last_vol = None
    last_ch = None

    for r in rows:
        if r["volume_title"] != last_vol:
            last_vol = r["volume_title"]
            last_ch = None
            toc_items.append(f'<li class="vol">{last_vol}</li>')
            body_parts.append(f'<h2 class="volume-title">{last_vol}</h2>')

        if r["chapter_title"] != last_ch:
            last_ch = r["chapter_title"]
            toc_items.append(f'<li class="ch">{last_ch}</li>')
            body_parts.append(f'<h3 class="chapter-title">{last_ch}</h3>')
            if r["summary"]:
                body_parts.append(f'<p class="chapter-summary">{r["summary"]}</p>')

        body_parts.append(f'<h4 class="section-title">第{r["section_order"]}节 {r["section_title"]}</h4>')
        if r["content"]:
            for para in r["content"].split('\n'):
                para = para.strip()
                if para:
                    body_parts.append(f'<p>{para}</p>')

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #1a1b26; --text: #c0caf5; --accent: #7aa2f7;
    --border: #3b4261; --card: #1f2335; --muted: #565f89;
    --green: #9ece6a;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    line-height: 1.8; max-width: 900px; margin: 0 auto; padding: 40px 20px;
  }}
  .header {{ text-align: center; margin-bottom: 40px; }}
  .header h1 {{ color: var(--accent); font-size: 2em; margin-bottom: 8px; }}
  .header .genre {{ color: var(--muted); font-size: 0.9em; }}
  .header .premise {{
    color: var(--text); margin-top: 16px; font-style: italic;
    border-left: 3px solid var(--accent); padding-left: 16px;
    text-align: left; max-width: 600px; margin-left: auto; margin-right: auto;
  }}
  .toc {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 24px 32px; margin-bottom: 40px;
  }}
  .toc h2 {{ color: var(--accent); font-size: 1.2em; margin-bottom: 12px; }}
  .toc ul {{ list-style: none; }}
  .toc .vol {{ font-weight: 600; margin-top: 12px; }}
  .toc .ch {{ padding-left: 20px; font-size: 0.95em; }}
  .toc a {{ color: var(--text); text-decoration: none; }}
  .toc a:hover {{ color: var(--accent); }}
  h2.volume-title {{
    color: var(--accent); font-size: 1.6em; margin-top: 48px;
    padding-bottom: 8px; border-bottom: 2px solid var(--border);
  }}
  h3.chapter-title {{
    color: var(--green); font-size: 1.3em; margin-top: 32px;
  }}
  .chapter-summary {{
    color: var(--muted); font-size: 0.9em; font-style: italic; margin-bottom: 12px;
  }}
  h4.section-title {{
    color: var(--text); font-size: 1.1em; margin-top: 24px;
  }}
  p {{ text-indent: 2em; margin-bottom: 8px; text-align: justify; }}
</style>
</head>
<body>
<div class="header">
  <h1>《{title}》</h1>
  <div class="genre">{genre}</div>
  <div class="premise">{premise}</div>
</div>
<div class="toc">
  <h2>📑 目录</h2>
  <ul>{''.join(toc_items)}</ul>
</div>
{''.join(body_parts)}
</body>
</html>"""

    return html


def get_volume_context(repo, current_node_id: int) -> str:
    """获取前卷全部 + 当前卷已写内容，用于续写衔接。"""
    if not repo:
        return ""

    row = repo.conn.execute(
        "SELECT volume_title FROM outline_nodes WHERE id=?",
        (current_node_id,)
    ).fetchone()
    if not row:
        return ""

    cur_vol = row["volume_title"]

    # 找到前一个卷
    prev_vols = repo.conn.execute(
        "SELECT DISTINCT volume_title FROM outline_nodes WHERE novel_id=? AND volume_title != '' "
        "AND sort_order < (SELECT sort_order FROM outline_nodes WHERE id=?) AND volume_title != ? "
        "ORDER BY sort_order DESC LIMIT 1",
        (repo.novel_id, current_node_id, cur_vol)
    ).fetchone()
    prev_vol = prev_vols["volume_title"] if prev_vols else None

    # 前卷全部 + 当前卷当前节之前
    if prev_vol:
        sections = repo.conn.execute(
            "SELECT o.volume_title, o.chapter_title, o.section_order, o.section_title, "
            "(SELECT s.content FROM sections s WHERE s.outline_node_id = o.id ORDER BY s.id DESC LIMIT 1) as content "
            "FROM outline_nodes o "
            "WHERE o.novel_id=? AND o.volume_title != '' AND o.status='done' "
            "AND o.sort_order < (SELECT sort_order FROM outline_nodes WHERE id=?) "
            "AND o.volume_title IN (?, ?) "
            "ORDER BY o.sort_order",
            (repo.novel_id, current_node_id, prev_vol, cur_vol)
        ).fetchall()
    else:
        sections = repo.conn.execute(
            "SELECT o.volume_title, o.chapter_title, o.section_order, o.section_title, "
            "(SELECT s.content FROM sections s WHERE s.outline_node_id = o.id ORDER BY s.id DESC LIMIT 1) as content "
            "FROM outline_nodes o "
            "WHERE o.novel_id=? AND o.volume_title != '' AND o.status='done' "
            "AND o.sort_order < (SELECT sort_order FROM outline_nodes WHERE id=?) "
            "AND o.volume_title = ? "
            "ORDER BY o.sort_order",
            (repo.novel_id, current_node_id, cur_vol)
        ).fetchall()

    if not sections:
        return ""

    parts = []
    last_content = ""
    for s in sections:
        parts.append(f"【{s['chapter_title']} · 第{s['section_order']}节 {s['section_title']}】")
        if s["content"]:
            parts.append(s["content"])
            last_content = s["content"]
        parts.append("")

    count = len(sections)
    if prev_vol:
        header = f"## 前情提要（{prev_vol} + {cur_vol}，共 {count} 节，请无缝衔接）\n"
    else:
        header = f"## 前情提要（{cur_vol}，共 {count} 节，请无缝衔接）\n"

    # 追加明确的接续提示：上一节最后几个完整段落
    tail = ""
    if last_content:
        # 按段落分割，取最后 2-3 段（约 150-300 字），保证是完整的句子
        paras = [p.strip() for p in last_content.split('\n') if p.strip()]
        if paras:
            anchor_paras = paras[-3:] if len(paras) >= 3 else paras
            anchor = '\n'.join(anchor_paras)
            tail = f"\n---\n⚠️ 上一节结尾（请从这里接续，不要另起开头）：\n{anchor}\n"

    return header + "\n".join(parts) + tail
