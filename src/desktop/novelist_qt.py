"""
小说家 — PyQt5 原生桌面应用
"""
import sys
import os

# 修复 Windows 下 Qt 平台插件找不到的问题
import PyQt5
_qt_plugins = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_qt_plugins, "platforms")
# 把 Qt bin 目录也加到 PATH（有些 DLL 需要）
_qt_bin = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "bin")
if os.path.exists(_qt_bin):
    os.environ["PATH"] = _qt_bin + ";" + os.environ.get("PATH", "")

import json, threading, time, re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QTabWidget, QLabel, QProgressBar, QStatusBar,
    QToolBar, QAction, QDockWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLineEdit, QSplitter, QMessageBox,
    QInputDialog, QComboBox, QTextBrowser, QListWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QIcon, QTextCursor, QColor

from src.db.novel_repository import NovelRepository
from src.agents.novelist import NovelistAgent
from src.models import LLMClient
from src.logging_config import info

# 默认小说想法
DEFAULT_IDEA = "一个996程序员在深夜加班时意外觉醒了修仙能力，从此在都市中潜行修炼，白天写代码，晚上斩妖除魔"
DEFAULT_GENRE = "都市"


class WriteThread(QThread):
    """后台写作线程——不阻塞 UI"""
    new_content = pyqtSignal(str)
    context_ready = pyqtSignal(str, int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, agent, repo, node_id, feedback=""):
        super().__init__()
        self.agent = agent
        self.repo = repo
        self.node_id = node_id
        self.feedback = feedback
        self._paused = False

    def pause(self): self._paused = True
    def resume(self): self._paused = False

    def run(self):
        try:
            ctx = self.repo.get_writing_context(self.node_id)
            self.context_ready.emit(ctx["context_text"], ctx["token_estimate"])

            node = self.repo.get_node(self.node_id)
            prompt = f"""请根据大纲写这一节内容。

{ctx['context_text']}

---
大纲: {node['title']}: {node.get('summary','自由发挥')}
{'反馈意见: '+self.feedback if self.feedback else ''}
要求: 800-2000字，保持角色和世界观一致。
写完后附上:
【本节摘要】: 2-3句话总结
"""

            raw = self.agent.llm.chat(
                "你是一位职业小说家。根据大纲和上下文写作，保持设定一致。",
                prompt
            )

            # 逐段发射
            for para in raw.split("\n\n"):
                if self._paused:
                    while self._paused:
                        time.sleep(0.1)
                if para.strip():
                    self.new_content.emit(para + "\n\n")
                    time.sleep(0.02)

            # 保存
            summary_match = re.search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)', raw)
            self.repo.save_section(self.node_id, raw, summary_match.group(1) if summary_match else "")
            self.repo.update_node_status(self.node_id, "done")

            self.finished.emit(self.repo.get_progress())

        except Exception as e:
            self.error.emit(str(e))


class NovelistWindow(QMainWindow):
    """小说家主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("📖 AI 小说家")
        self.resize(1400, 850)

        self.agent: NovelistAgent = None
        self.repo: NovelRepository = None
        self.write_thread: WriteThread = None
        self.current_node_id: int = None
        self.outline_data: list = []

        self._init_ui()
        self._init_menu()
        self._init_toolbar()
        self._status("就绪")

    # ================================================================
    # UI 构建
    # ================================================================

    def _init_ui(self):
        central = QSplitter(Qt.Horizontal)

        # ---- 左侧：大纲树 ----
        self.outline_tree = QTreeWidget()
        self.outline_tree.setHeaderLabel("📋 大纲")
        self.outline_tree.setMinimumWidth(250)
        self.outline_tree.itemClicked.connect(self._on_outline_clicked)
        central.addWidget(self.outline_tree)

        # ---- 中间：写作区 ----
        mid = QWidget()
        mid_layout = QVBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)

        # 上下文提示
        self.context_label = QLabel("")
        self.context_label.setStyleSheet(
            "background:#1a1a2e;color:#f0c060;padding:6px 10px;font-size:11px;border-radius:4px;"
        )
        self.context_label.setMaximumHeight(80)
        self.context_label.setWordWrap(True)
        self.context_label.hide()
        mid_layout.addWidget(self.context_label)

        # 写作区
        self.content_edit = QTextEdit()
        self.content_edit.setReadOnly(True)
        self.content_edit.setFont(QFont("Microsoft YaHei", 12))
        self.content_edit.setStyleSheet(
            "QTextEdit{background:#0d0d1a;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:6px;padding:16px;}"
        )
        self.content_edit.setPlaceholderText("👈 点击左侧大纲某一节，然后点「▶ 开始写」")
        mid_layout.addWidget(self.content_edit)

        # 底部控制栏
        ctrl_bar = QHBoxLayout()

        self.btn_start = QPushButton("▶ 开始写")
        self.btn_start.clicked.connect(self._start_write)
        self.btn_start.setStyleSheet(self._btn_style("#7c5ce7", "#fff"))

        self.btn_pause = QPushButton("⏸ 暂停")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setStyleSheet(self._btn_style("#f0c060", "#000"))

        self.btn_next = QPushButton("⏭ 下一节")
        self.btn_next.clicked.connect(self._next_section)
        self.btn_next.setStyleSheet(self._btn_style("#00d2a0", "#000"))

        self.feedback_input = QLineEdit()
        self.feedback_input.setPlaceholderText("输入反馈意见后按回车...")
        self.feedback_input.returnPressed.connect(self._send_feedback)
        self.feedback_input.setStyleSheet(
            "QLineEdit{background:#0a0a14;color:#d0d0d8;border:1px solid #2a2a3a;border-radius:6px;padding:8px;}"
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(
            "QProgressBar{background:#1a1a2e;border:none;height:6px;border-radius:3px}"
            "QProgressBar::chunk{background:#7c5ce7;border-radius:3px}"
        )
        self.progress_bar.setTextVisible(False)

        ctrl_bar.addWidget(self.btn_start)
        ctrl_bar.addWidget(self.btn_pause)
        ctrl_bar.addWidget(self.btn_next)
        ctrl_bar.addWidget(self.feedback_input)
        ctrl_bar.addWidget(self.progress_bar)
        mid_layout.addLayout(ctrl_bar)

        central.addWidget(mid)

        # ---- 右侧：信息面板 ----
        right = QTabWidget()
        right.setMinimumWidth(260)

        self.char_list = QTextBrowser()
        self.char_list.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.char_list, "👥 角色")

        self.thread_list = QTextBrowser()
        self.thread_list.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.thread_list, "📌 伏笔")

        self.rule_list = QTextBrowser()
        self.rule_list.setStyleSheet("background:#0d0d1a;color:#d0d0d8;border:none;padding:8px;")
        right.addTab(self.rule_list, "🌍 世界观")

        central.addWidget(right)
        central.setSizes([280, 780, 280])
        self.setCentralWidget(central)

    def _init_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")
        
        new_act = QAction("新建小说", self)
        new_act.triggered.connect(self._new_novel)
        file_menu.addAction(new_act)
        
        file_menu.addSeparator()
        
        exit_act = QAction("退出", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

    def _init_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        
        genre_label = QLabel(" 类型: ")
        tb.addWidget(genre_label)
        self.genre_combo = QComboBox()
        self.genre_combo.addItems(["玄幻","科幻","都市","悬疑","言情","历史"])
        self.genre_combo.setStyleSheet("QComboBox{background:#1a1a2e;color:#d0d0d8;padding:4px;}")
        tb.addWidget(self.genre_combo)
        
        tb.addSeparator()
        
        status_btn = QPushButton("📊 统计")
        status_btn.clicked.connect(self._show_status)
        status_btn.setStyleSheet(self._btn_style("#2a2a3a", "#d0d0d8"))
        tb.addWidget(status_btn)
        
        self.addToolBar(tb)

    def _status(self, msg):
        self.statusBar().showMessage(msg)

    # ================================================================
    # 新建小说
    # ================================================================

    def _new_novel(self):
        idea, ok = QInputDialog.getText(
            self, "新建小说", "💡 想写什么故事？",
            text=DEFAULT_IDEA
        )
        if not ok or not idea.strip():
            return

        genre = self.genre_combo.currentText()
        self._status(f"正在构思《{idea[:20]}...》...")

        # 后台线程初始化
        class InitThread(QThread):
            done = pyqtSignal(object, object)
            def run(self):
                agent = NovelistAgent(LLMClient())
                novel = agent.init_novel(idea, genre)
                repo = NovelRepository(f"novel_{int(time.time())}")
                # 创建大纲
                repo.conn.execute(
                    "INSERT INTO novels (id,title,genre,premise,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (repo.novel_id, novel.title, genre, novel.premise, "draft",
                     __import__('datetime').datetime.now().isoformat(),
                     __import__('datetime').datetime.now().isoformat())
                )
                # 三层大纲: 3卷 × 3章 × 3节
                sort = 0
                for v in range(1, 4):
                    repo.conn.execute(
                        "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                        (repo.novel_id, None, "volume", sort, f"第{v}卷", "", "pending"))
                    vid = repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    sort += 1
                    for c in range(1, 4):
                        repo.conn.execute(
                            "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                            (repo.novel_id, vid, "chapter", sort, f"第{v}卷第{c}章", "", "pending"))
                        cid = repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                        sort += 1
                        for s in range(1, 4):
                            repo.conn.execute(
                                "INSERT INTO outline_nodes (novel_id,parent_id,level,sort_order,title,summary,status) VALUES (?,?,?,?,?,?,?)",
                                (repo.novel_id, cid, "section", sort, f"第{v}卷第{c}章第{s}节", "", "pending"))
                            sort += 1
                repo.conn.commit()
                # 保存角色
                for ch in novel.characters:
                    repo.conn.execute(
                        "INSERT INTO characters (novel_id,name,role,traits,arc,updated_at) VALUES (?,?,?,?,?,?)",
                        (repo.novel_id, ch.name, ch.role, ch.description, "", __import__('datetime').datetime.now().isoformat()))
                repo.conn.commit()
                self.done.emit(agent, repo)

        self.init_thread = InitThread()
        self.init_thread.done.connect(self._on_init_done)
        self.init_thread.start()

    def _on_init_done(self, agent, repo):
        self.agent = agent
        self.repo = repo
        self.outline_data = repo.get_outline_tree()
        self._refresh_outline()
        self._refresh_info()
        self._status(f"✅ {agent.novel.title} — {len(self.outline_data)} 个节点")
        self.setWindowTitle(f"📖 {agent.novel.title} — AI 小说家")

    # ================================================================
    # 大纲树
    # ================================================================

    def _refresh_outline(self):
        self.outline_tree.clear()
        if not self.outline_data:
            return

        # 构建层级结构
        nodes_by_parent = {}
        roots = []
        for n in self.outline_data:
            pid = n.get("parent_id") or 0
            nodes_by_parent.setdefault(pid, []).append(n)
            if pid == 0 or pid is None:
                roots.append(n)

        def add_children(parent_item, parent_id):
            for n in nodes_by_parent.get(parent_id, []):
                icon = {"volume": "📘", "chapter": "📄", "section": "📝"}.get(n["level"], "")
                done = "✅ " if n["status"] == "done" else ""
                item = QTreeWidgetItem(parent_item or self.outline_tree,
                                       [f"{done}{icon} {n['title']}"])
                item.setData(0, Qt.UserRole, n["id"])
                if n["status"] == "done":
                    item.setForeground(0, QColor("#00d2a0"))
                add_children(item, n["id"])

        for r in roots:
            add_children(None, r["id"])

        self.outline_tree.expandAll()

    def _on_outline_clicked(self, item):
        node_id = item.data(0, Qt.UserRole)
        if node_id:
            self.current_node_id = node_id
            node = next((n for n in self.outline_data if n["id"] == node_id), None)
            if node and node["level"] == "section":
                self._status(f"已选择: {node['title']}")
                self.content_edit.setPlaceholderText(f"已选择: {node['title']}\n点击「▶ 开始写」开始写作")

    # ================================================================
    # 写作控制
    # ================================================================

    def _start_write(self):
        if not self.current_node_id:
            QMessageBox.information(self, "提示", "请先在左侧大纲选择一节")
            return
        if not self.repo:
            QMessageBox.information(self, "提示", "请先新建小说（文件→新建小说）")
            return

        self.content_edit.clear()
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)

        feedback = self.feedback_input.text().strip()
        self.feedback_input.clear()

        self.write_thread = WriteThread(self.agent, self.repo, self.current_node_id, feedback)
        self.write_thread.context_ready.connect(self._on_context)
        self.write_thread.new_content.connect(self._on_content)
        self.write_thread.finished.connect(self._on_finish)
        self.write_thread.error.connect(self._on_error)
        self.write_thread.start()

        self._status("✍️ 写作中...")

    def _toggle_pause(self):
        if not self.write_thread:
            return
        if self.write_thread._paused:
            self.write_thread.resume()
            self.btn_pause.setText("⏸ 暂停")
            self._status("✍️ 写作中...")
        else:
            self.write_thread.pause()
            self.btn_pause.setText("▶ 继续")
            self._status("⏸ 已暂停")

    def _send_feedback(self):
        feedback = self.feedback_input.text().strip()
        if feedback:
            self.content_edit.append(f"\n\n[💬 反馈: {feedback}]\n\n")
            self.feedback_input.clear()
            self._start_write()

    def _next_section(self):
        if not self.current_node_id or not self.outline_data:
            return
        idx = next((i for i, n in enumerate(self.outline_data) if n["id"] == self.current_node_id), -1)
        for i in range(idx + 1, len(self.outline_data)):
            if self.outline_data[i]["level"] == "section":
                self.current_node_id = self.outline_data[i]["id"]
                self._start_write()
                return
        QMessageBox.information(self, "提示", "已经是最后一节了！")

    # ================================================================
    # 信号回调
    # ================================================================

    def _on_context(self, text, tokens):
        self.context_label.setText(f"🧠 注入上下文 (~{tokens} tokens)")
        self.context_label.show()

    def _on_content(self, text):
        cursor = self.content_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.content_edit.ensureCursorVisible()

    def _on_finish(self, progress):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ 暂停")
        self.context_label.hide()
        self._status(f"✅ 完成 — 总进度 {progress.get('progress_pct',0)}%")
        self.progress_bar.setValue(int(progress.get("progress_pct", 0)))
        self.outline_data = self.repo.get_outline_tree()
        self._refresh_outline()
        self._refresh_info()

    def _on_error(self, err):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self._status(f"❌ 错误: {err}")
        QMessageBox.critical(self, "错误", err)

    def _refresh_info(self):
        if not self.repo: return
        p = self.repo.get_progress()
        self.progress_bar.setValue(int(p.get("progress_pct", 0)))
        self.char_list.setText(f"角色数: {p.get('characters',0)}\n活跃伏笔: {p.get('open_threads',0)}\n字数: {p.get('total_words',0):,}")

    def _show_status(self):
        if not self.repo:
            QMessageBox.information(self, "统计", "请先新建小说")
            return
        p = self.repo.get_progress()
        QMessageBox.information(self, "📊 写作统计",
            f"总章节: {p['done_sections']}/{p['total_sections']}\n"
            f"总字数: {p['total_words']:,}\n"
            f"角色: {p['characters']}人\n活跃伏笔: {p['open_threads']}条\n"
            f"进度: {p['progress_pct']}%")

    # ================================================================
    # 样式
    # ================================================================

    def _btn_style(self, bg, fg):
        return f"QPushButton{{background:{bg};color:{fg};border:none;border-radius:6px;padding:8px 16px;font-size:13px;font-weight:600}}QPushButton:hover{{opacity:0.9}}QPushButton:disabled{{background:#1a1a2e;color:#555}}"


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 全局暗色主题
    app.setStyleSheet("""
        QMainWindow{background:#0f0f14}
        QTreeWidget{background:#13131f;color:#d0d0d8;border:1px solid #1e1e32;font-size:13px}
        QTreeWidget::item:hover{background:#1e1e35}
        QTreeWidget::item:selected{background:#7c5ce7}
        QSplitter::handle{background:#1e1e32;width:2px}
        QStatusBar{background:#13131f;color:#888;border-top:1px solid #1e1e32}
        QToolBar{background:#13131f;border-bottom:1px solid #1e1e32;spacing:8px;padding:4px}
        QTabWidget::pane{background:#0d0d1a;border:1px solid #1e1e32}
        QTabBar::tab{background:#13131f;color:#888;padding:6px 16px;border:1px solid #1e1e32}
        QTabBar::tab:selected{background:#1e1e35;color:#d0d0d8}
    """)

    window = NovelistWindow()
    window.show()

    # 自动弹出新建小说对话框
    QTimer.singleShot(500, window._new_novel)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
