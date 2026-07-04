"""
小说家桌面端 — 三阶段渐进式（重构）
============================================================
阶段1: 构思 → AI 生成梗概+角色+世界观，用户打磨
阶段2: 大纲 → 基于构思细化卷章结构，用户调整
阶段3: 写作 → 分层上下文注入，逐节写
"""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Qt 插件路径
import PyQt5
_qt_dir = os.path.dirname(PyQt5.__file__)
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_qt_dir, "Qt5", "plugins", "platforms")
_qt_bin = os.path.join(_qt_dir, "Qt5", "bin")
if os.path.exists(_qt_bin):
    os.environ["PATH"] = _qt_bin + ";" + os.environ.get("PATH", "")

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QTextBrowser, QLabel, QProgressBar,
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QSplitter, QMessageBox,
    QInputDialog, QStackedWidget, QListWidget, QListWidgetItem,
    QToolBar, QAction, QStatusBar,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QColor

from config import load_config
from src.models.llm_client import chat as llm_chat
from src.db.novel_repository import NovelRepository
from src.db.session_store import SessionStore
from src.context.builder import SmartContextBuilder


class LLMThread(QThread):
    """后台 LLM 调用"""
    result = pyqtSignal(str)
    def __init__(self, config, system, user):
        super().__init__()
        self.cfg, self.system, self.user = config, system, user
    def run(self):
        try:
            r = llm_chat(self.cfg, self.system, self.user)
            self.result.emit(r)
        except Exception as e:
            self.result.emit(f"❌ {e}")


# ---- 阶段提示词（各不相同，不套固定模板）----

IDEA_SYSTEM = """你是小说创作顾问。用户有一个故事想法，你帮他扩展成详细的创作方案。

请用 JSON 返回:
{
  "title": "小说标题",
  "premise": "一句话梗概（30字内）",
  "genre": "类型",
  "world_building": "世界观简述（100字内）",
  "characters": [
    {"name":"角色名","role":"主角/配角/反派","traits":"外貌性格特点"}
  ],
  "suggested_volumes": 3,
  "hook": "吸引读者的核心看点"
}"""

OUTLINE_SYSTEM = """你是小说大纲策划。根据已有的故事设定，帮用户规划章节结构。

请用 JSON 返回:
{
  "volumes": [
    {
      "title": "第X卷标题",
      "chapters": [
        {"title": "章节标题", "summary": "本章内容概要（30字）", "sections": 3}
      ]
    }
  ]
}

要求:
- 每卷3-6章，每章2-4节
- 有明确起承转合
- 和已有角色/世界观设定保持一致"""

WRITE_SYSTEM = """你是职业小说家。根据上下文写一节内容(800-2000字)。
保持角色性格一致，世界观自洽，情节连贯。"""


class Phase1Widget(QWidget):
    """阶段1: 构思打磨"""
    phase_done = pyqtSignal(dict)  # 返回构思 JSON

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.cfg = config
        layout = QVBoxLayout(self)

        title = QLabel("💡 阶段1: 构思打磨")
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#7c5ce7")
        layout.addWidget(title)

        layout.addWidget(QLabel("输入你的故事想法，AI 帮你扩展为完整构思"))
        self.idea_input = QTextEdit()
        self.idea_input.setPlaceholderText("比如: 一个996程序员在深夜加班时意外觉醒了修仙能力...")
        self.idea_input.setMaximumHeight(80)
        self.idea_input.setStyleSheet("background:#0a0a14;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:8px;padding:10px;")
        layout.addWidget(self.idea_input)

        btn_row = QHBoxLayout()
        self.gen_btn = QPushButton("🚀 生成构思")
        self.gen_btn.clicked.connect(self._generate)
        self.gen_btn.setStyleSheet("background:#7c5ce7;color:#fff;padding:10px 20px;border-radius:8px;font-weight:bold")
        btn_row.addWidget(self.gen_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status = QLabel("")
        layout.addWidget(self.status)

        self.output = QTextBrowser()
        self.output.setStyleSheet("background:#0a0a14;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:8px;padding:10px;")
        self.output.setMinimumHeight(300)
        layout.addWidget(self.output)

        self.approve_btn = QPushButton("✅ 确认构思，进入大纲阶段")
        self.approve_btn.clicked.connect(self._approve)
        self.approve_btn.setEnabled(False)
        self.approve_btn.setStyleSheet("background:#00d2a0;color:#000;padding:10px;border-radius:8px;font-weight:bold")
        layout.addWidget(self.approve_btn)

        self._result_data = None

    def _generate(self):
        idea = self.idea_input.toPlainText().strip()
        if not idea: return
        self.gen_btn.setEnabled(False)
        self.status.setText("⏳ 生成中...")
        self.thread = LLMThread(self.cfg, IDEA_SYSTEM, f"故事想法: {idea}")
        self.thread.result.connect(self._on_result)
        self.thread.start()

    def _on_result(self, raw):
        self.gen_btn.setEnabled(True)
        self.status.setText("✅ 完成")
        # 解析 JSON
        import json
        try:
            js = raw
            if "```json" in js: js = js.split("```json")[1].split("```")[0]
            elif "```" in js: js = js.split("```")[1].split("```")[0]
            data = json.loads(js.strip())
        except:
            data = {"title": "未命名", "premise": raw[:100], "genre": "未知", "world_building": "", "characters": [], "hook": ""}

        self._result_data = data
        chars = "\n".join(f"  - {c['name']}({c.get('role','')}): {c.get('traits','')}" for c in data.get("characters", []))
        self.output.setHtml(f"""
        <h2>{data.get('title','')}</h2>
        <p><b>类型:</b> {data.get('genre','')} | <b>看点:</b> {data.get('hook','')}</p>
        <p><b>梗概:</b> {data.get('premise','')}</p>
        <h3>世界观</h3><p>{data.get('world_building','')}</p>
        <h3>角色</h3><pre>{chars}</pre>
        """)
        self.approve_btn.setEnabled(True)

    def _approve(self):
        if self._result_data:
            self.phase_done.emit(self._result_data)


class Phase2Widget(QWidget):
    """阶段2: 大纲细化"""
    phase_done = pyqtSignal(list)  # 返回大纲列表

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.cfg = config
        layout = QVBoxLayout(self)

        title = QLabel("📋 阶段2: 大纲细化")
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#7c5ce7")
        layout.addWidget(title)

        layout.addWidget(QLabel("AI 根据构思生成章节大纲，你可以调整卷数、每卷章数"))
        row = QHBoxLayout()
        row.addWidget(QLabel("卷数:"))
        self.vol_spin = QInputDialog()
        self.vol_input = QLineEdit("3")
        self.vol_input.setMaximumWidth(50)
        self.vol_input.setStyleSheet("background:#0a0a14;color:#d0d0d8;padding:6px;border:1px solid #2a2a3a;border-radius:6px;")
        row.addWidget(self.vol_input)
        row.addWidget(QLabel("每卷章数:"))
        self.ch_input = QLineEdit("4")
        self.ch_input.setMaximumWidth(50)
        self.ch_input.setStyleSheet("background:#0a0a14;color:#d0d0d8;padding:6px;border:1px solid #2a2a3a;border-radius:6px;")
        row.addWidget(self.ch_input)
        row.addStretch()
        layout.addLayout(row)

        self.gen_btn = QPushButton("📋 生成大纲")
        self.gen_btn.clicked.connect(self._generate)
        self.gen_btn.setStyleSheet("background:#7c5ce7;color:#fff;padding:10px 20px;border-radius:8px;font-weight:bold")
        layout.addWidget(self.gen_btn)

        self.status = QLabel("")
        layout.addWidget(self.status)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("大纲")
        self.tree.setStyleSheet("background:#0a0a14;color:#d0d0d8;border:1px solid #2a2a3a;")
        self.tree.setMinimumHeight(300)
        layout.addWidget(self.tree)

        self.approve_btn = QPushButton("✅ 确认大纲，开始写作")
        self.approve_btn.clicked.connect(self._approve)
        self.approve_btn.setEnabled(False)
        self.approve_btn.setStyleSheet("background:#00d2a0;color:#000;padding:10px;border-radius:8px;font-weight:bold")
        layout.addWidget(self.approve_btn)

        self._outline = []

    def set_idea_data(self, data: dict):
        self._idea_data = data

    def _generate(self):
        if not hasattr(self, '_idea_data'): return
        self.gen_btn.setEnabled(False)
        self.status.setText("⏳ 生成大纲...")

        import json
        idea_json = json.dumps(self._idea_data, ensure_ascii=False)
        vols = self.vol_input.text() or "3"
        chs = self.ch_input.text() or "4"
        user = f"已有设定:\n{idea_json}\n\n请规划 {vols} 卷，每卷约 {chs} 章的大纲。"

        self.thread = LLMThread(self.cfg, OUTLINE_SYSTEM, user)
        self.thread.result.connect(self._on_result)
        self.thread.start()

    def _on_result(self, raw):
        self.gen_btn.setEnabled(True)
        self.status.setText("✅ 大纲生成完成")
        import json
        try:
            js = raw
            if "```json" in js: js = js.split("```json")[1].split("```")[0]
            elif "```" in js: js = js.split("```")[1].split("```")[0]
            data = json.loads(js.strip())
        except:
            data = {"volumes": [{"title": "第1卷", "chapters": [{"title": "开始", "summary": "一切从这里开始", "sections": 3}]}]}

        self.tree.clear()
        self._outline = []
        for v_idx, vol in enumerate(data.get("volumes", []), 1):
            vol_item = QTreeWidgetItem(self.tree, [f"📘 第{v_idx}卷 {vol.get('title','')}"])
            for c_idx, ch in enumerate(vol.get("chapters", []), 1):
                ch_item = QTreeWidgetItem(vol_item, [f"📄 第{c_idx}章 {ch.get('title','')}"])
                for s_idx in range(ch.get("sections", 3)):
                    QTreeWidgetItem(ch_item, [f"📝 第{s_idx+1}节"])
                self._outline.append({"volume": v_idx, "chapter": c_idx, "title": ch.get("title",""),
                                      "summary": ch.get("summary",""), "sections": ch.get("sections", 3)})
            vol_item.setExpanded(True)
        # 展开第一个卷
        if self.tree.topLevelItemCount() > 0:
            self.tree.topLevelItem(0).setExpanded(True)

        self.approve_btn.setEnabled(True)

    def _approve(self):
        self.phase_done.emit(self._outline)


class Phase3Widget(QWidget):
    """阶段3: 逐节写作"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.repo = None
        self.session = None
        self.builder = None
        self.current_node_id = None
        layout = QVBoxLayout(self)

        title = QLabel("✍️ 阶段3: 写作")
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#7c5ce7")
        layout.addWidget(title)

        split = QSplitter(Qt.Horizontal)

        # 左: 大纲
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("大纲")
        self.tree.setMinimumWidth(220)
        self.tree.setStyleSheet("background:#0a0a14;color:#d0d0d8;border:1px solid #2a2a3a;")
        self.tree.itemClicked.connect(lambda i,_: self._select_node(i.data(0, Qt.UserRole)))
        split.addWidget(self.tree)

        # 右: 写作区
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0,0,0,0)

        self.ctx_label = QLabel("")
        self.ctx_label.setStyleSheet("background:#1a1a2e;color:#f0c060;padding:6px 10px;font-size:11px;border-radius:4px;")
        self.ctx_label.setMaximumHeight(60); self.ctx_label.setWordWrap(True); self.ctx_label.hide()
        rl.addWidget(self.ctx_label)

        self.content = QTextEdit()
        self.content.setReadOnly(True)
        self.content.setFont(QFont("Microsoft YaHei", 12))
        self.content.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:6px;padding:12px;")
        self.content.setPlaceholderText("👈 点击左侧大纲某一节，点「开始写」")
        rl.addWidget(self.content)

        bar = QHBoxLayout()
        self.btn_start = QPushButton("▶ 开始写")
        self.btn_start.clicked.connect(self._start)
        self.btn_start.setStyleSheet("background:#7c5ce7;color:#fff;padding:8px 16px;border-radius:6px;font-weight:bold")
        self.fb = QLineEdit()
        self.fb.setPlaceholderText("反馈..."); self.fb.returnPressed.connect(self._start)
        self.fb.setStyleSheet("background:#0a0a14;color:#d0d0d8;padding:8px;border:1px solid #2a2a3a;border-radius:6px;")
        bar.addWidget(self.btn_start); bar.addWidget(self.fb)
        rl.addLayout(bar)

        split.addWidget(right)
        split.setSizes([250, 750])
        layout.addWidget(split)

    def init_project(self, idea_data: dict, outline: list):
        """根据构思和大纲初始化数据库"""
        self.repo = NovelRepository(f"novel_{int(time.time())}")
        now = __import__('datetime').datetime.now().isoformat()

        self.repo.conn.execute(
            "INSERT INTO novels VALUES (?,?,?,?,?,?,?,?)",
            (self.repo.novel_id, idea_data.get("title","未命名"), idea_data.get("genre",""),
             idea_data.get("premise",""), "draft", 0, now, now))

        # 保存角色
        for c in idea_data.get("characters", []):
            self.repo.conn.execute(
                "INSERT INTO characters (novel_id,name,role,traits,arc,updated_at) VALUES (?,?,?,?,?,?)",
                (self.repo.novel_id, c["name"], c.get("role",""), c.get("traits",""), "", now))

        # 保存世界观
        self.repo.conn.execute(
            "INSERT INTO story_bible (project_id,category,key,value,source_scene,updated_at) VALUES (?,?,?,?,?,?)",
            (self.repo.novel_id, "world_rule", "世界观", idea_data.get("world_building",""), 0, now))

        # 大纲→数据库节点
        sort = 0; node_map = {}
        for v_idx in sorted(set(o["volume"] for o in outline)):
            vid = self._add_node(None, "volume", sort, f"第{v_idx}卷", ""); sort += 1
            for o in [x for x in outline if x["volume"] == v_idx]:
                cid = self._add_node(vid, "chapter", sort, f"第{o['volume']}卷第{o['chapter']}章 {o['title']}", o.get("summary",""))
                sort += 1
                for s in range(o.get("sections", 3)):
                    sid = self._add_node(cid, "section", sort, f"第{o['volume']}卷第{o['chapter']}章第{s+1}节", ""); sort += 1
                    node_map[f"{o['volume']}-{o['chapter']}-{s+1}"] = sid

        self.repo.conn.commit()
        self._refresh_tree()
        self.session = SessionStore(self.repo.novel_id)
        self.session.start_session()
        self.builder = SmartContextBuilder(None, self.session)  # builder 稍后完善

    def _add_node(self, parent_id, level, sort, title, summary):
        self.repo.conn.execute(
            "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
            (self.repo.novel_id, parent_id, level, sort, title, summary, "pending"))
        return self.repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _refresh_tree(self):
        if not self.repo: return
        self.tree.clear()
        data = self.repo.get_outline_tree()
        nodes_by_pid = {}
        for n in data:
            nodes_by_pid.setdefault(n.get("parent_id") or 0, []).append(n)

        def add(parent, pid):
            for n in nodes_by_pid.get(pid, []):
                icon = {"volume":"📘","chapter":"📄","section":"📝"}.get(n["level"],"")
                done = "✅ " if n["status"] == "done" else ""
                item = QTreeWidgetItem(parent or self.tree, [f"{done}{icon} {n['title']}"])
                item.setData(0, Qt.UserRole, n["id"])
                if n["status"] == "done": item.setForeground(0, QColor("#00d2a0"))
                add(item, n["id"])

        for r in nodes_by_pid.get(0, []): add(None, r["id"])
        self.tree.expandAll()

    def _select_node(self, nid):
        if nid: self.current_node_id = nid

    def _start(self):
        if not self.current_node_id or not self.repo: return
        self.content.clear()
        self.btn_start.setEnabled(False)

        fb = self.fb.text().strip(); self.fb.clear()

        ctx = self.repo.get_writing_context(self.current_node_id)
        context_text = ctx["context_text"]
        self.ctx_label.setText(f"🧠 ~{ctx['token_estimate']} tokens"); self.ctx_label.show()

        node = self.repo.get_node(self.current_node_id)
        # 阶段3提示词：简洁，不用展示全部角色设定（已注入 context_text）
        system = "你是职业小说家。根据上下文写一节(800-2000字)。保持设定一致，情节连贯。"
        user = f"{context_text}\n\n---\n大纲: {node['title']}\n{'反馈: '+fb if fb else ''}\n请写本节:"

        self.thread = LLMThread(self.cfg, system, user)
        self.thread.result.connect(self._on_done)
        self.thread.start()

    def _on_done(self, raw):
        self.content.setPlainText(raw)
        self.btn_start.setEnabled(True)
        self.ctx_label.hide()
        if self.repo and self.current_node_id:
            m = re.search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)', raw)
            self.repo.save_section(self.current_node_id, raw, m.group(1) if m else "")
            self.repo.update_node_status(self.current_node_id, "done")
            self._refresh_tree()


class NovelistWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📖 AI 小说家")
        self.resize(1200, 800)
        self.config = load_config()

        self.stack = QStackedWidget()
        self.phase1 = Phase1Widget(self.config)
        self.phase2 = Phase2Widget(self.config)
        self.phase3 = Phase3Widget(self.config)

        self.phase1.phase_done.connect(self._on_phase1_done)
        self.phase2.phase_done.connect(self._on_phase2_done)

        self.stack.addWidget(self.phase1)
        self.stack.addWidget(self.phase2)
        self.stack.addWidget(self.phase3)
        self.setCentralWidget(self.stack)

        self.statusBar().showMessage("阶段1: 输入想法 → AI 生成构思")

    def _on_phase1_done(self, data):
        self._idea_data = data
        self.phase2.set_idea_data(data)
        self.stack.setCurrentIndex(1)
        self.statusBar().showMessage("阶段2: 确认大纲结构 → AI 细化")
        QTimer.singleShot(300, self.phase2._generate)

    def _on_phase2_done(self, outline):
        self.phase3.init_project(self._idea_data, outline)
        self.stack.setCurrentIndex(2)
        self.statusBar().showMessage("阶段3: 点击左侧大纲开始写作")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow{background:#0f0f14} QTreeWidget{background:#13131f;color:#d0d0d8;font-size:13px}
        QTreeWidget::item:hover{background:#1e1e35} QTreeWidget::item:selected{background:#7c5ce7}
        QStatusBar{background:#13131f;color:#888;border-top:1px solid #1e1e32}
    """)
    w = NovelistWindow(); w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
