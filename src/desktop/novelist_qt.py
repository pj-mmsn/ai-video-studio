"""
小说家 — PyQt5 原生桌面应用（重构版）
============================================================
架构: 配置→Agent→Repository 全在主线程，只有 LLM 网络调用走 QThread
"""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QTabWidget, QLabel, QProgressBar,
    QToolBar, QAction, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QSplitter, QMessageBox,
    QInputDialog, QComboBox, QTextBrowser, QStatusBar,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QColor

from config import load_config
from src.models.llm_client import chat as llm_chat
from src.agents.novelist import NovelistAgent, NOVELIST_SYSTEM
from src.db.novel_repository import NovelRepository
from src.db.session_store import SessionStore


class WriteThread(QThread):
    """网络调用线程——LLM请求 + Redis上下文管理"""
    chunk = pyqtSignal(str)
    context_ready = pyqtSignal(str, int)
    overflow = pyqtSignal(dict)         # 上下文超限信号（主线程处理flush）
    done = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self, config, repo, session, node_id, feedback=""):
        super().__init__()
        self.cfg = config
        self.repo = repo
        self.session = session
        self.node_id = node_id
        self.feedback = feedback
        self._paused = False

    def pause(self): self._paused = True
    def resume(self): self._paused = False

    def run(self):
        try:
            # 1. 从 SQL 加载上下文到 Redis
            sql_ctx = self.repo.get_writing_context(self.node_id)
            self.session.load_context({
                "current_node_id": self.node_id,
                "context_text": sql_ctx["context_text"],
                "characters": sql_ctx.get("characters", []),
                "threads": sql_ctx.get("threads", []),
                "rules": sql_ctx.get("rules", []),
                "recent_summaries": sql_ctx.get("recent_summaries", []),
                "token_estimate": sql_ctx["token_estimate"],
            })
            self.context_ready.emit(sql_ctx["context_text"], sql_ctx["token_estimate"])

            # 2. 检查上下文是否超限
            if self.session.check_overflow(max_tokens=6000):
                flushed = self.session.trim_context()
                if flushed:
                    self.overflow.emit(flushed)

            # 3. 从 Redis 读上下文用于 LLM 调用
            ctx = self.session.get_context()
            node = self.repo.get_node(self.node_id)

            system = "你是一位职业小说家。根据大纲和上下文写作，保持设定一致。"
            user = f"""{ctx['context_text']}

---
大纲: {node['title']}: {node.get('summary','自由发挥')}
{'反馈意见: '+self.feedback if self.feedback else ''}
要求: 800-2000字，保持角色和世界观一致。
写完后附上:
【本节摘要】: 2-3句话总结"""

            raw = llm_chat(self.cfg, system, user)

            for para in raw.split("\n\n"):
                while self._paused:
                    __import__('time').sleep(0.1)
                if para.strip():
                    self.chunk.emit(para + "\n\n")
                    __import__('time').sleep(0.02)

            m = __import__('re').search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)', raw)
            summary = m.group(1) if m else ""

            # 4. 更新 Redis 上下文
            self.session.update_after_write(self.node_id, summary)

            self.done.emit(raw, summary)

        except Exception as e:
            self.error.emit(str(e))


class NovelistWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📖 AI 小说家")
        self.resize(1400, 850)

        # 状态
        self.config = load_config()
        self.agent = None
        self.repo = None
        self.session = None        # Redis 会话层
        self.write_thread = None
        self.current_node_id = None
        self.outline_data = []

        self._init_ui()
        self._init_menu()
        self._status("就绪 — 文件→新建小说")

    # ================================================================
    # UI
    # ================================================================
    def _init_ui(self):
        c = QSplitter(Qt.Horizontal)

        # 左: 大纲
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("📋 大纲")
        self.tree.setMinimumWidth(250)
        self.tree.itemClicked.connect(lambda i,_: self._select_node(i.data(0, Qt.UserRole)))
        c.addWidget(self.tree)

        # 中: 写作区
        mid = QWidget()
        ml = QVBoxLayout(mid); ml.setContentsMargins(0,0,0,0)

        self.ctx_label = QLabel("")
        self.ctx_label.setStyleSheet("background:#1a1a2e;color:#f0c060;padding:6px 10px;font-size:11px;border-radius:4px;")
        self.ctx_label.setMaximumHeight(60); self.ctx_label.setWordWrap(True); self.ctx_label.hide()
        ml.addWidget(self.ctx_label)

        self.content = QTextEdit()
        self.content.setReadOnly(True)
        self.content.setFont(QFont("Microsoft YaHei", 12))
        self.content.setStyleSheet("QTextEdit{background:#0d0d1a;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:6px;padding:16px;}")
        self.content.setPlaceholderText("👈 点击左侧大纲某一节，然后点「▶ 开始写」")
        ml.addWidget(self.content)

        # 控制栏
        bar = QHBoxLayout()
        self.btn_start = self._btn("▶ 开始写", "#7c5ce7", "#fff", self._start)
        self.btn_pause = self._btn("⏸ 暂停", "#f0c060", "#000", self._toggle_pause, False)
        self.btn_next = self._btn("⏭ 下一节", "#00d2a0", "#000", self._next)
        self.fb = QLineEdit()
        self.fb.setPlaceholderText("反馈意见（回车发送）...")
        self.fb.returnPressed.connect(self._send_feedback)
        self.fb.setStyleSheet("QLineEdit{background:#0a0a14;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:6px;padding:8px;}")
        self.prog = QProgressBar()
        self.prog.setStyleSheet("QProgressBar{background:#1a1a2e;border:none;height:6px;border-radius:3px}QProgressBar::chunk{background:#7c5ce7;border-radius:3px}")
        self.prog.setTextVisible(False)

        bar.addWidget(self.btn_start); bar.addWidget(self.btn_pause)
        bar.addWidget(self.btn_next); bar.addWidget(self.fb); bar.addWidget(self.prog)
        ml.addLayout(bar)
        c.addWidget(mid)

        # 右: 信息
        right = QTabWidget(); right.setMinimumWidth(260)
        self.char_list = QTextBrowser()
        self.char_list.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.char_list, "👥 角色")
        self.thread_list = QTextBrowser()
        self.thread_list.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.thread_list, "📌 伏笔")
        self.rule_list = QTextBrowser()
        self.rule_list.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.rule_list, "🌍 世界观")
        c.addWidget(right)
        c.setSizes([280, 780, 280])
        self.setCentralWidget(c)

    def _init_menu(self):
        m = self.menuBar().addMenu("文件")
        m.addAction("新建小说").triggered.connect(self._new_novel)
        m.addSeparator()
        m.addAction("退出").triggered.connect(self.close)

    def _btn(self, text, bg, fg, handler, enabled=True):
        b = QPushButton(text)
        b.clicked.connect(handler)
        b.setEnabled(enabled)
        b.setStyleSheet(f"QPushButton{{background:{bg};color:{fg};border:none;border-radius:6px;padding:8px 16px;font-weight:600}}QPushButton:hover{{opacity:0.9}}QPushButton:disabled{{background:#1a1a2e;color:#555}}")
        return b

    def _status(self, msg):
        self.statusBar().showMessage(msg)

    # ================================================================
    # 新建小说——主线程直接操作
    # ================================================================
    def _new_novel(self):
        idea, ok = QInputDialog.getText(self, "新建小说", "💡 想写什么故事？",
            text="一个996程序员在深夜加班时意外觉醒了修仙能力")
        if not ok or not idea.strip(): return

        self.config = load_config()  # 重新加载配置
        self.agent = NovelistAgent(self.config)
        self._status("正在构思...")
        QApplication.processEvents()  # 刷新 UI

        # 初始化（主线程）
        novel = self.agent.init_novel(idea, "都市")
        self.repo = NovelRepository(f"novel_{int(time.time())}")
        
        # 写数据库
        from datetime import datetime
        now = datetime.now().isoformat()
        self.repo.conn.execute(
            "INSERT INTO novels VALUES (?,?,?,?,?,?,?)",
            (self.repo.novel_id, novel.title, "都市", novel.premise, "draft", now, now))
        self.repo.conn.commit()

        # 三层大纲
        sort = 0
        for v in range(1, 4):
            self.repo.conn.execute(
                "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                (self.repo.novel_id, None, "volume", sort, f"第{v}卷", "", "pending"))
            vid = self.repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]; sort += 1
            for c in range(1, 4):
                self.repo.conn.execute(
                    "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                    (self.repo.novel_id, vid, "chapter", sort, f"第{v}卷第{c}章", "", "pending"))
                cid = self.repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]; sort += 1
                for s in range(1, 4):
                    self.repo.conn.execute(
                        "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                        (self.repo.novel_id, cid, "section", sort, f"第{v}卷第{c}章第{s}节", "", "pending"))
                    sort += 1
        self.repo.conn.commit()

        for ch in novel.characters:
            self.repo.conn.execute(
                "INSERT INTO characters (novel_id,name,role,traits,arc,updated_at) VALUES (?,?,?,?,?,?)",
                (self.repo.novel_id, ch.name, ch.role, ch.description, "", now))
        self.repo.conn.commit()

        self.outline_data = self.repo.get_outline_tree()
        self._refresh_tree()
        self._refresh_info()

        # 启动 Redis 会话
        self.session = SessionStore(self.repo.novel_id)
        status = self.session.start_session()
        redis_status = "Redis" if status["redis"] else "内存"
        self._status(f"✅ {novel.title} | 会话: {redis_status}模式")
        self.setWindowTitle(f"📖 {novel.title} — AI 小说家")

    # ================================================================
    # 大纲树
    # ================================================================
    def _refresh_tree(self):
        self.tree.clear()
        if not self.outline_data: return
        nodes_by_pid = {}
        roots = []
        for n in self.outline_data:
            nodes_by_pid.setdefault(n.get("parent_id") or 0, []).append(n)
            if not n.get("parent_id"): roots.append(n)

        def add(parent, pid):
            for n in nodes_by_pid.get(pid, []):
                icon = {"volume":"📘","chapter":"📄","section":"📝"}.get(n["level"],"")
                done = "✅ " if n["status"] == "done" else ""
                item = QTreeWidgetItem(parent or self.tree, [f"{done}{icon} {n['title']}"])
                item.setData(0, Qt.UserRole, n["id"])
                if n["status"] == "done": item.setForeground(0, QColor("#00d2a0"))
                add(item, n["id"])

        for r in roots: add(None, r["id"])
        self.tree.expandAll()

    def _select_node(self, nid):
        if nid:
            self.current_node_id = nid
            node = next((n for n in self.outline_data if n["id"] == nid), None)
            if node:
                self._status(f"已选择: {node['title']}")
                self.content.setPlaceholderText(f"已选择: {node['title']}\n点击「▶ 开始写」")

    # ================================================================
    # 写作控制
    # ================================================================
    def _start(self):
        if not self.current_node_id or not self.repo: return
        self.content.clear()
        self.btn_start.setEnabled(False); self.btn_pause.setEnabled(True)

        fb = self.fb.text().strip(); self.fb.clear()

        self.write_thread = WriteThread(self.config, self.repo, self.session, self.current_node_id, fb)
        self.write_thread.context_ready.connect(lambda t, n: (self.ctx_label.setText(f"🧠 ~{n} tokens"), self.ctx_label.show()))
        self.write_thread.chunk.connect(self._on_chunk)
        self.write_thread.done.connect(self._on_done)
        self.write_thread.overflow.connect(self._on_overflow)
        self.write_thread.error.connect(lambda e: QMessageBox.critical(self, "错误", e))
        self.write_thread.start()
        self._status("✍️ 写作中...")

    def _on_chunk(self, text):
        c = self.content.textCursor(); c.movePosition(QTextCursor.End); c.insertText(text)
        self.content.ensureCursorVisible()

    def _on_done(self, raw, summary):
        self.repo.save_section(self.current_node_id, raw, summary)
        self.repo.update_node_status(self.current_node_id, "done")
        self.btn_start.setEnabled(True); self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ 暂停"); self.ctx_label.hide()
        self._status(f"✅ 完成 | Redis sessions: {self.session._get('sections_written') or '0'}节")
        p = self.repo.get_progress()
        self.prog.setValue(int(p.get("progress_pct", 0)))
        self.outline_data = self.repo.get_outline_tree()
        self._refresh_tree(); self._refresh_info()

    def _on_overflow(self, flushed):
        """Redis 上下文超限——旧摘要写入 SQL，Redis 只保留热的"""
        if flushed.get("flushed_summary"):
            self.repo.conn.execute(
                "INSERT INTO story_bible (project_id,category,key,value,source_scene,updated_at) VALUES (?,?,?,?,?,?)",
                (self.repo.novel_id, "session_summary", f"auto_{int(__import__('time').time())}",
                 flushed["flushed_summary"], 0, __import__('datetime').datetime.now().isoformat()))
            self.repo.conn.commit()
            self._status(f"🔄 上下文裁剪: 保留最近{flushed.get('remaining_count',0)}条")

    def _toggle_pause(self):
        if not self.write_thread: return
        if self.write_thread._paused:
            self.write_thread.resume(); self.btn_pause.setText("⏸ 暂停")
        else:
            self.write_thread.pause(); self.btn_pause.setText("▶ 继续")

    def _send_feedback(self):
        fb = self.fb.text().strip()
        if fb:
            self.content.append(f"\n\n[💬 {fb}]\n\n"); self.fb.clear(); self._start()

    def _next(self):
        if not self.current_node_id or not self.outline_data: return
        idx = next((i for i,n in enumerate(self.outline_data) if n["id"]==self.current_node_id), -1)
        for i in range(idx+1, len(self.outline_data)):
            if self.outline_data[i]["level"] == "section":
                self.current_node_id = self.outline_data[i]["id"]; self._start(); return
        QMessageBox.information(self, "提示", "已是最后一节！")

    def _refresh_info(self):
        if not self.repo: return
        p = self.repo.get_progress()
        self.prog.setValue(int(p.get("progress_pct", 0)))
        self.char_list.setText(f"角色: {p.get('characters',0)}\n字数: {p.get('total_words',0):,}\n伏笔: {p.get('open_threads',0)}")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow{background:#0f0f14} QTreeWidget{background:#13131f;color:#d0d0d8;border:1px solid #1e1e32;font-size:13px}
        QTreeWidget::item:hover{background:#1e1e35} QTreeWidget::item:selected{background:#7c5ce7}
        QSplitter::handle{background:#1e1e32;width:2px} QStatusBar{background:#13131f;color:#888;border-top:1px solid #1e1e32}
        QTabWidget::pane{background:#0d0d1a;border:1px solid #1e1e32}
        QTabBar::tab{background:#13131f;color:#888;padding:6px 16px} QTabBar::tab:selected{background:#1e1e35;color:#d0d0d8}
    """)
    w = NovelistWindow(); w.show()
    QTimer.singleShot(500, w._new_novel)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
