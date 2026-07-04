"""
小说家桌面端 — 多模式循环编辑器
============================================================
模式自由切换，每次切换上下文自动适配:
  💡 构思模式 → 轻量上下文（梗概+角色草案）
  📋 大纲模式 → 结构上下文（卷章关系+节奏）
  ✍️ 写作模式 → 完整四层上下文（角色+世界观+前文+大纲）
"""
import sys, os, re, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import PyQt5
_qt_dir = os.path.dirname(PyQt5.__file__)
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_qt_dir, "Qt5", "plugins", "platforms")
_qt_bin = os.path.join(_qt_dir, "Qt5", "bin")
if os.path.exists(_qt_bin): os.environ["PATH"] = _qt_bin + ";" + os.environ.get("PATH", "")

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor

from config import load_config
from src.models.llm_client import chat_stream  # 改为流式
from src.db.novel_repository import NovelRepository


# ---- 流式 LLM 线程 ----
class LLMThread(QThread):
    chunk = pyqtSignal(str)      # 每收到一段就发射
    done = pyqtSignal(str)       # 全部完成
    error = pyqtSignal(str)

    def __init__(self, config, system, user):
        super().__init__()
        self.c = config; self.s = system; self.u = user
        self._paused = False

    def pause(self): self._paused = True
    def resume(self): self._paused = False

    def run(self):
        try:
            full = []
            def on_chunk(text):
                full.append(text)
                self.chunk.emit(text)

            result = chat_stream(self.c, self.s, self.u, on_chunk=on_chunk)
            self.done.emit(result or "".join(full))
        except Exception as e:
            self.error.emit(str(e))


# ---- 三种模式的系统提示词 ----
PROMPTS = {
    "idea": """你是小说创作顾问。根据用户想法扩展为创作方案。JSON:
{"title":"","premise":"30字梗概","genre":"","hook":"核心看点","world_building":"100字世界观",
 "characters":[{"name":"","role":"主角/配角","traits":"外貌性格"}]}""",

    "outline": """你是小说大纲策划。根据已有设定规划章节结构。JSON:
{"volumes":[{"title":"","chapters":[{"title":"","summary":"30字概要","sections":3}]}]}
要求: 有起承转合，和已有角色/世界观一致""",

    "write": """你是职业小说家。根据上下文写本节(800-2000字)。
保持角色一致、世界观自洽、情节连贯。写完后附【本节摘要】一句话。""",
}


class NovelistWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📖 AI 小说家")
        self.resize(1300, 850)
        self.cfg = load_config()
        self.repo = None
        self._mode = "idea"  # idea | outline | write
        self._idea_data = {}

        self._init_ui()
        self._status("💡 输入故事想法，开始构思")

    # ================================================================
    # UI
    # ================================================================
    def _init_ui(self):
        c = QSplitter(Qt.Horizontal)

        # ---- 左侧: 信息面板（随模式变化）----
        self.info_stack = QStackedWidget()

        # 构思模式面板
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.addWidget(QLabel("💡 故事想法"))
        self.idea_input = QTextEdit()
        self.idea_input.setPlaceholderText("输入你的故事想法...\n例: 996程序员加班时觉醒修仙能力")
        self.idea_input.setMaximumHeight(80)
        self.idea_input.setStyleSheet(self._input_style())
        l1.addWidget(self.idea_input)
        self.idea_btn = QPushButton("🚀 生成构思")
        self.idea_btn.clicked.connect(lambda: self._llm("idea"))
        self.idea_btn.setStyleSheet(self._btn("bg"))
        l1.addWidget(self.idea_btn)
        l1.addStretch()
        self.info_stack.addWidget(p1)

        # 大纲模式面板
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.addWidget(QLabel("📋 大纲结构"))
        row = QHBoxLayout()
        row.addWidget(QLabel("卷:")); self.vol_in = QLineEdit("3"); self.vol_in.setMaximumWidth(40)
        self.vol_in.setStyleSheet(self._input_style()); row.addWidget(self.vol_in)
        row.addWidget(QLabel("章/卷:")); self.ch_in = QLineEdit("4"); self.ch_in.setMaximumWidth(40)
        self.ch_in.setStyleSheet(self._input_style()); row.addWidget(self.ch_in)
        row.addStretch(); l2.addLayout(row)
        self.outline_btn = QPushButton("📋 生成/刷新大纲")
        self.outline_btn.clicked.connect(lambda: self._llm("outline"))
        self.outline_btn.setStyleSheet(self._btn("bg"))
        l2.addWidget(self.outline_btn)
        l2.addStretch()
        self.info_stack.addWidget(p2)

        # 写作模式面板
        p3 = QWidget()
        l3 = QVBoxLayout(p3)
        l3.addWidget(QLabel("🎯 当前进度"))
        self.progress_label = QLabel("未开始")
        self.progress_label.setStyleSheet("color:#00d2a0;font-size:14px;font-weight:bold;")
        l3.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar{background:#1a1a2e;border:none;height:6px;border-radius:3px}QProgressBar::chunk{background:#7c5ce7;border-radius:3px}")
        self.progress_bar.setTextVisible(False)
        l3.addWidget(self.progress_bar)
        l3.addWidget(QLabel("🧠 本次上下文"))
        self.ctx_label = QLabel("")
        self.ctx_label.setStyleSheet("background:#1a1a2e;color:#f0c060;padding:8px;border-radius:6px;font-size:11px;")
        self.ctx_label.setWordWrap(True)
        l3.addWidget(self.ctx_label)
        l3.addStretch()
        self.info_stack.addWidget(p3)

        c.addWidget(self.info_stack)

        # ---- 中间: 大纲树 + 写作区 ----
        mid = QSplitter(Qt.Vertical)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("📋 大纲")
        self.tree.setMinimumHeight(150)
        self.tree.itemClicked.connect(lambda i,_: self._on_tree_click(i))
        self.tree.setStyleSheet("background:#0a0a14;color:#d0d0d8;font-size:13px;border:1px solid #2a2a3a;")
        mid.addWidget(self.tree)

        self.content = QTextEdit()
        self.content.setReadOnly(True)
        self.content.setFont(QFont("Microsoft YaHei", 12))
        self.content.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:6px;padding:12px;")
        self.content.setPlaceholderText("输出区——构思、大纲、正文都在这里显示")
        mid.addWidget(self.content)
        mid.setSizes([200, 500])

        c.addWidget(mid)

        # ---- 右侧: 角色/世界观 ----
        right = QTabWidget()
        self.char_view = QTextBrowser()
        self.char_view.setStyleSheet("background:#0a0a14;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.char_view, "👥 角色")
        self.world_view = QTextBrowser()
        self.world_view.setStyleSheet("background:#0a0a14;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.world_view, "🌍 世界观")
        c.addWidget(right)
        c.setSizes([280, 650, 280])
        self.setCentralWidget(c)

        # ---- 底部控制栏 ----
        ctrl = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["💡 构思模式", "📋 大纲模式", "✍️ 写作模式"])
        self.mode_combo.currentIndexChanged.connect(self._switch_mode)
        self.mode_combo.setStyleSheet("QComboBox{background:#1a1a2e;color:#d0d0d8;padding:6px 12px;font-size:14px;border:1px solid #2a2a3a;border-radius:6px}")
        ctrl.addWidget(self.mode_combo)
        ctrl.addStretch()

        self.fb_input = QLineEdit()
        self.fb_input.setPlaceholderText("输入反馈后按回车...")
        self.fb_input.returnPressed.connect(self._send_feedback)
        self.fb_input.setStyleSheet(self._input_style())
        ctrl.addWidget(self.fb_input)

        self.act_btn = QPushButton("▶ 执行")
        self.act_btn.clicked.connect(self._execute)
        self.act_btn.setStyleSheet(self._btn("bg"))
        ctrl.addWidget(self.act_btn)

        # 把控制栏放到底部
        bottom_bar = QWidget()
        bottom_bar.setLayout(ctrl)
        bottom_bar.setStyleSheet("background:#13131f;border-top:1px solid #1e1e32;")
        # 用 central widget 的布局加底部栏
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.addWidget(c)
        main_layout.addWidget(bottom_bar)
        central = QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    # ================================================================
    # 模式切换
    # ================================================================
    def _switch_mode(self, idx):
        modes = ["idea", "outline", "write"]
        self._mode = modes[idx]
        self.info_stack.setCurrentIndex(idx)
        self._status(f"切换到: {self.mode_combo.currentText()}")

    # ================================================================
    # 统一入口：根据当前模式决定发什么
    # ================================================================
    def _execute(self):
        mode = self._mode
        if mode == "idea":
            self._gen_idea()
        elif mode == "outline":
            self._gen_outline()
        elif mode == "write":
            self._write_section()

    def _llm(self, mode_tag, extra_user=""):
        """统一 LLM 调用——流式输出到 content 区域"""
        # 构思模式
        if mode_tag == "idea":
            idea = self.idea_input.toPlainText().strip()
            if not idea: return
            self.content.clear()
            self._status("⏳ 生成构思中...")
            self.thread = LLMThread(self.cfg, PROMPTS["idea"], f"故事想法: {idea}")
            self.thread.chunk.connect(self._on_chunk)
            self.thread.done.connect(self._on_idea_result)
            self.thread.error.connect(lambda e: self.content.setPlainText(f"❌ {e}"))

        # 大纲模式
        elif mode_tag == "outline":
            if not self._idea_data:
                self.content.setPlainText("请先在构思模式生成故事设定")
                return
            self.content.clear()
            self._status("⏳ 生成大纲中...")
            vols = self.vol_in.text() or "3"; chs = self.ch_in.text() or "4"
            user = f"已有设定:\n{json.dumps(self._idea_data, ensure_ascii=False)}\n\n请规划约{vols}卷，每卷约{chs}章的大纲。{extra_user}"
            self.thread = LLMThread(self.cfg, PROMPTS["outline"], user)
            self.thread.chunk.connect(self._on_chunk)
            self.thread.done.connect(self._on_outline_result)
            self.thread.error.connect(lambda e: self.content.setPlainText(f"❌ {e}"))

        # 写作模式
        elif mode_tag == "write":
            if not self.repo or not hasattr(self, '_current_node_id'):
                self.content.setPlainText("请先生成大纲，然后点击左侧大纲某一节")
                return
            self.content.clear()
            self._status("✍️ 写作中...")
            self.act_btn.setEnabled(False)

            ctx = self.repo.get_writing_context(self._current_node_id)
            self.ctx_label.setText(f"🧠 ~{ctx['token_estimate']} tokens")
            node = self.repo.get_node(self._current_node_id)
            fb = self.fb_input.text().strip(); self.fb_input.clear()

            user = f"{ctx['context_text']}\n\n---\n大纲: {node['title']}\n{'反馈: '+fb if fb else ''}\n请写本节:"
            self.thread = LLMThread(self.cfg, PROMPTS["write"], user)
            self.thread.chunk.connect(self._on_chunk)
            self.thread.done.connect(self._on_write_result)
            self.thread.error.connect(lambda e: self.content.setPlainText(f"❌ {e}"))

        self.thread.start()

    def _on_chunk(self, text):
        """实时追加文本到输出区"""
        c = self.content.textCursor()
        c.movePosition(QTextCursor.End)
        c.insertText(text)
        self.content.ensureCursorVisible()

    def _gen_idea(self): self._llm("idea")
    def _gen_outline(self): self._llm("outline")
    def _write_section(self): self._llm("write")

    # ================================================================
    # 结果处理
    # ================================================================
    def _on_idea_result(self, raw):
        data = self._parse_json(raw)
        self._idea_data = data
        chars = "\n".join(f"  {c['name']}({c.get('role','')}): {c.get('traits','')}" for c in data.get("characters", []))
        self.content.setHtml(f"""
        <h2>{data.get('title','未命名')}</h2>
        <p><b>{data.get('genre','')}</b> | 看点: {data.get('hook','')}</p>
        <blockquote>{data.get('premise','')}</blockquote>
        <h3>世界观</h3><p>{data.get('world_building','')}</p>
        <h3>角色</h3><pre>{chars}</pre>
        """)
        self.char_view.setText(chars)
        self.world_view.setText(data.get('world_building',''))
        self._status("✅ 构思完成——切换到大纲模式")

        # 立即初始化数据库
        if not self.repo:
            self._init_db(data)

    def _on_outline_result(self, raw):
        data = self._parse_json(raw)
        self.tree.clear()
        if not self.repo: self._init_db(self._idea_data)

        # 清除旧大纲节点重建
        self.repo.conn.execute("DELETE FROM outline_nodes WHERE novel_id=?", (self.repo.novel_id,))
        sort = 0
        self._outline_data = []
        for v_idx, vol in enumerate(data.get("volumes", []), 1):
            vid = self._add_db_node(None, "volume", sort, f"第{v_idx}卷 {vol.get('title','')}", ""); sort += 1
            vol_item = QTreeWidgetItem(self.tree, [f"📘 第{v_idx}卷 {vol.get('title','')}"])
            vol_item.setData(0, Qt.UserRole, vid)
            for c_idx, ch in enumerate(vol.get("chapters", []), 1):
                cid = self._add_db_node(vid, "chapter", sort, f"第{v_idx}卷第{c_idx}章 {ch.get('title','')}", ch.get("summary",""))
                sort += 1
                ch_item = QTreeWidgetItem(vol_item, [f"📄 第{c_idx}章 {ch.get('title','')}"])
                ch_item.setData(0, Qt.UserRole, cid)
                for s_idx in range(ch.get("sections", 3)):
                    sid = self._add_db_node(cid, "section", sort, f"第{v_idx}卷第{c_idx}章第{s_idx+1}节", ""); sort += 1
                    QTreeWidgetItem(ch_item, [f"📝 第{s_idx+1}节"]).setData(0, Qt.UserRole, sid)
                ch_item.setExpanded(True)
            vol_item.setExpanded(True)
        self.repo.conn.commit()
        self.content.setPlainText("✅ 大纲已生成——切换到写作模式，点击左侧某一节开始写")
        self._status("✅ 大纲完成——切换到写作模式")

    def _on_write_result(self, raw):
        self.content.setPlainText(raw)
        self.act_btn.setEnabled(True)
        if self.repo and hasattr(self, '_current_node_id'):
            m = re.search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)', raw)
            self.repo.save_section(self._current_node_id, raw, m.group(1) if m else "")
            self.repo.update_node_status(self._current_node_id, "done")
            self._refresh_tree_status()
            p = self.repo.get_progress()
            self.progress_bar.setValue(int(p.get("progress_pct", 0)))
            self.progress_label.setText(f"{p['done_sections']}/{p['total_sections']} 节 | {p['total_words']:,} 字")

    # ================================================================
    # 辅助
    # ================================================================
    def _init_db(self, data):
        self.repo = NovelRepository(f"novel_{int(time.time())}")
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.repo.conn.execute("INSERT INTO novels VALUES (?,?,?,?,?,?,?,?)",
            (self.repo.novel_id, data.get("title",""), data.get("genre",""), data.get("premise",""), "draft", 0, now, now))
        for c in data.get("characters", []):
            self.repo.conn.execute("INSERT INTO characters (novel_id,name,role,traits,arc,updated_at) VALUES (?,?,?,?,?,?)",
                (self.repo.novel_id, c["name"], c.get("role",""), c.get("traits",""), "", now))
        self.repo.conn.execute("INSERT INTO story_bible (project_id,category,key,value,source_scene,updated_at) VALUES (?,?,?,?,?,?)",
            (self.repo.novel_id, "world_rule", "世界观", data.get("world_building",""), 0, now))
        self.repo.conn.commit()

    def _add_db_node(self, pid, level, sort, title, summary):
        self.repo.conn.execute("INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
            (self.repo.novel_id, pid, level, sort, title, summary, "pending"))
        return self.repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _on_tree_click(self, item):
        nid = item.data(0, Qt.UserRole)
        if nid and self.repo:
            self._current_node_id = nid
            node = self.repo.get_node(nid)
            if node:
                self._status(f"已选: {node['title']}")

    def _refresh_tree_status(self):
        if not self.repo: return
        data = self.repo.get_outline_tree()
        def update(item):
            nid = item.data(0, Qt.UserRole)
            if nid:
                node = next((n for n in data if n["id"] == nid), None)
                if node and node["status"] == "done":
                    item.setForeground(0, QColor("#00d2a0"))
            for i in range(item.childCount()): update(item.child(i))
        for i in range(self.tree.topLevelItemCount()): update(self.tree.topLevelItem(i))

    def _send_feedback(self):
        if self._mode == "write":
            self._write_section()

    def _parse_json(self, raw):
        try:
            js = raw
            if "```json" in js: js = js.split("```json")[1].split("```")[0]
            elif "```" in js: js = js.split("```")[1].split("```")[0]
            return json.loads(js.strip())
        except: return {}

    def _status(self, msg): self.statusBar().showMessage(msg)

    def _input_style(self):
        return "background:#0a0a14;color:#d0d0d8;padding:8px;border:1px solid #2a2a3a;border-radius:6px;"

    def _btn(self, color):
        return f"background:{'#7c5ce7' if color=='bg' else color};color:#fff;padding:8px 20px;border:none;border-radius:6px;font-weight:bold;"


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow{background:#0f0f14} QTreeWidget{background:#13131f;color:#d0d0d8}
        QTreeWidget::item:hover{background:#1e1e35} QTreeWidget::item:selected{background:#7c5ce7}
        QStatusBar{background:#13131f;color:#888;border-top:1px solid #1e1e32}
        QTabWidget::pane{background:#0d0d1a;border:1px solid #1e1e32}
        QTabBar::tab{background:#13131f;color:#888;padding:6px 16px} QTabBar::tab:selected{background:#1e1e35;color:#d0d0d8}
    """)
    w = NovelistWindow(); w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
