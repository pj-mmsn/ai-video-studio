"""
小说家桌面端 — 专业写作编辑器
"""
import sys, os, re, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import PyQt5
_qt_dir = os.path.dirname(PyQt5.__file__)
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_qt_dir, "Qt5", "plugins", "platforms")
_qt_bin = os.path.join(_qt_dir, "Qt5", "bin")
if os.path.exists(_qt_bin): os.environ["PATH"] = _qt_bin + ";" + os.environ.get("PATH", "")

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont, QTextCursor, QColor, QPalette, QIcon

from config import load_config
from src.models.llm_client import chat_stream
from src.db.novel_repository import NovelRepository

# ---- 配色 ----
C = {
    "bg":           "#0d1117",
    "surface":      "#161b22",
    "surface2":     "#21262d",
    "border":       "#30363d",
    "accent":       "#7c5ce7",
    "accent2":      "#6c4fd6",
    "text":         "#e6edf3",
    "text2":        "#8b949e",
    "green":        "#3fb950",
    "yellow":       "#d2991d",
    "red":          "#f85149",
    "blue":         "#58a6ff",
}

STYLE = f"""
QMainWindow{{background:{C['bg']}}}
QTreeWidget{{
    background:{C['surface']}; color:{C['text']}; border:1px solid {C['border']};
    border-radius:8px; padding:4px; font-size:13px; outline:none;
}}
QTreeWidget::item{{padding:5px 8px; border-radius:4px;}}
QTreeWidget::item:hover{{background:{C['surface2']};}}
QTreeWidget::item:selected{{background:{C['accent']}; color:#fff;}}
QTextEdit, QTextBrowser{{
    background:{C['bg']}; color:{C['text']}; border:1px solid {C['border']};
    border-radius:8px; padding:16px; font-size:14px; line-height:1.8;
    selection-background:{C['accent']};
}}
QLineEdit{{
    background:{C['surface']}; color:{C['text']}; border:1px solid {C['border']};
    border-radius:6px; padding:8px 12px; font-size:13px;
}}
QLineEdit:focus{{border-color:{C['accent']};}}
QComboBox{{
    background:{C['surface2']}; color:{C['text']}; border:1px solid {C['border']};
    border-radius:6px; padding:6px 12px; font-size:13px;
}}
QComboBox:hover{{border-color:{C['accent']};}}
QComboBox::drop-down{{border:none; width:20px;}}
QProgressBar{{
    background:{C['surface']}; border:none; height:4px; border-radius:2px;
}}
QProgressBar::chunk{{background:{C['green']}; border-radius:2px;}}
QStatusBar{{background:{C['surface']}; color:{C['text2']}; border-top:1px solid {C['border']}; font-size:12px;}}
QTabWidget::pane{{background:{C['bg']}; border:1px solid {C['border']}; border-radius:8px;}}
QTabBar::tab{{
    background:{C['surface']}; color:{C['text2']}; padding:8px 16px;
    border:1px solid {C['border']}; border-bottom:none; font-size:13px;
}}
QTabBar::tab:selected{{background:{C['bg']}; color:{C['accent']};}}
QScrollBar:vertical{{
    background:{C['bg']}; width:8px; border-radius:4px;
}}
QScrollBar::handle:vertical{{
    background:{C['border']}; border-radius:4px; min-height:30px;
}}
QScrollBar::handle:vertical:hover{{background:{C['text2']};}}
QScrollBar::add-line, QScrollBar::sub-line{{height:0;}}
"""

# ---- 提示词 ----
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

# ---- 流式 LLM 线程 ----
class LLMThread(QThread):
    chunk = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)
    def __init__(self, config, system, user):
        super().__init__(); self.c = config; self.s = system; self.u = user
    def run(self):
        try:
            full = []
            def on_chunk(text): full.append(text); self.chunk.emit(text)
            result = chat_stream(self.c, self.s, self.u, on_chunk=on_chunk)
            self.done.emit(result or "".join(full))
        except Exception as e: self.error.emit(str(e))


class TabBtn(QPushButton):
    """模式切换按钮"""
    def __init__(self, text, icon):
        super().__init__(f"  {icon}  {text}")
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton{{
                background:transparent; color:{C['text2']}; border:none;
                text-align:left; padding:8px 16px; font-size:13px; font-weight:500;
                border-left:2px solid transparent;
            }}
            QPushButton:hover{{background:{C['surface2']}; color:{C['text']};}}
            QPushButton:checked{{
                background:{C['surface2']}; color:{C['accent']}; font-weight:600;
                border-left:2px solid {C['accent']};
            }}
        """)


class NovelistWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 小说家")
        self.resize(1400, 880)
        self.setMinimumSize(1000, 600)
        self.cfg = load_config()
        self.repo = None
        self._mode = "idea"
        self._idea_data = {}
        self._current_node_id = None
        self._outline_data = []

        self._init_ui()
        self._status("就绪 — 扫描已有项目...")

        # 扫描已有项目
        existing = self._scan_projects()
        if existing:
            self._show_project_dialog(existing)
        else:
            self._status("就绪 — 输入故事想法开始创作")

    def _init_ui(self):
        # 中央分割器
        split = QSplitter(Qt.Horizontal)

        # ====== 左侧边栏 ======
        sidebar = QWidget()
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet(f"background:{C['surface']}; border-right:1px solid {C['border']};")
        sl = QVBoxLayout(sidebar); sl.setContentsMargins(0,0,0,0); sl.setSpacing(0)

        # Logo
        logo = QLabel("  📖 AI 小说家")
        logo.setStyleSheet(f"font-size:18px;font-weight:bold;color:{C['text']}; padding:16px;")
        sl.addWidget(logo)

        # 项目信息
        self.project_label = QLabel("  未创建项目")
        self.project_label.setStyleSheet(f"color:{C['text2']};font-size:12px;padding:4px 16px 12px;")
        sl.addWidget(self.project_label)

        # 模式切换按钮组
        sl.addWidget(QLabel(f"  <span style='color:{C['text2']};font-size:11px;'>创作模式</span>"))
        self.tab_idea = TabBtn("构思", "💡")
        self.tab_outline = TabBtn("大纲", "📋")
        self.tab_write = TabBtn("写作", "✍️")
        self.tab_idea.setChecked(True)
        for btn in [self.tab_idea, self.tab_outline, self.tab_write]:
            sl.addWidget(btn)

        # 按钮互斥
        self._tab_group = QButtonGroup(self)
        self._tab_group.addButton(self.tab_idea, 0)
        self._tab_group.addButton(self.tab_outline, 1)
        self._tab_group.addButton(self.tab_write, 2)
        self._tab_group.buttonClicked[int].connect(self._switch_mode)

        sl.addSpacing(16)

        # 模式面板（堆叠切换）
        self.info_stack = QStackedWidget()
        self.info_stack.setStyleSheet(f"padding:8px 16px;")

        # -- 构思面板 --
        p1 = QWidget(); l1 = QVBoxLayout(p1); l1.setContentsMargins(0,0,0,0)
        l1.addWidget(QLabel(f"<span style='color:{C['text2']};font-size:11px;'>故事想法</span>"))
        self.idea_input = QTextEdit()
        self.idea_input.setPlaceholderText("输入你的故事想法...\n\n例: 996程序员在深夜加班时觉醒修仙能力")
        self.idea_input.setMaximumHeight(100)
        l1.addWidget(self.idea_input)
        l1.addSpacing(8)
        self.idea_btn = QPushButton("  🚀  生成构思")
        self.idea_btn.clicked.connect(lambda: self._llm("idea"))
        self.idea_btn.setCursor(Qt.PointingHandCursor)
        self.idea_btn.setStyleSheet(f"""
            QPushButton{{background:{C['accent']};color:#fff;border:none;border-radius:8px;
            padding:10px;font-size:13px;font-weight:600;}}
            QPushButton:hover{{background:{C['accent2']};}}
            QPushButton:disabled{{background:{C['surface2']};color:{C['text2']};}}
        """)
        l1.addWidget(self.idea_btn)
        l1.addStretch()
        self.info_stack.addWidget(p1)

        # -- 大纲面板 --
        p2 = QWidget(); l2 = QVBoxLayout(p2); l2.setContentsMargins(0,0,0,0)
        l2.addWidget(QLabel(f"<span style='color:{C['text2']};font-size:11px;'>章节结构</span>"))
        row = QHBoxLayout()
        row.addWidget(QLabel(f"<span style='color:{C['text2']}'>卷</span>"))
        self.vol_in = QLineEdit("3"); self.vol_in.setFixedWidth(50); row.addWidget(self.vol_in)
        row.addWidget(QLabel(f"<span style='color:{C['text2']}'>章/卷</span>"))
        self.ch_in = QLineEdit("4"); self.ch_in.setFixedWidth(50); row.addWidget(self.ch_in)
        row.addStretch(); l2.addLayout(row)
        l2.addSpacing(8)
        self.outline_btn = QPushButton("  📋  生成大纲")
        self.outline_btn.clicked.connect(lambda: self._llm("outline"))
        self.outline_btn.setCursor(Qt.PointingHandCursor)
        self.outline_btn.setStyleSheet(self.idea_btn.styleSheet())
        l2.addWidget(self.outline_btn)
        l2.addStretch()
        self.info_stack.addWidget(p2)

        # -- 写作面板 --
        p3 = QWidget(); l3 = QVBoxLayout(p3); l3.setContentsMargins(0,0,0,0)
        l3.addWidget(QLabel(f"<span style='color:{C['text2']};font-size:11px;'>写作进度</span>"))
        self.progress_label = QLabel("未开始")
        self.progress_label.setStyleSheet(f"color:{C['green']};font-size:18px;font-weight:bold;")
        l3.addWidget(self.progress_label)
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(False)
        l3.addWidget(self.progress_bar)
        l3.addSpacing(8)
        self.ctx_label = QLabel("")
        self.ctx_label.setStyleSheet(f"background:{C['bg']};color:{C['yellow']};padding:10px;border-radius:6px;font-size:11px;")
        self.ctx_label.setWordWrap(True)
        self.ctx_label.hide()
        l3.addWidget(self.ctx_label)
        l3.addStretch()
        self.info_stack.addWidget(p3)

        sl.addWidget(self.info_stack)
        sl.addStretch()

        # 底部信息
        info = QLabel(f"  <span style='color:{C['text2']};font-size:10px;'>模型: {self.cfg['model']}</span>")
        info.setStyleSheet(f"padding:12px 16px;")
        sl.addWidget(info)

        split.addWidget(sidebar)

        # ====== 中间: 大纲树 + 输出区 ======
        mid = QSplitter(Qt.Vertical)

        # 大纲树
        tree_header = QWidget()
        th = QHBoxLayout(tree_header); th.setContentsMargins(0,0,0,0)
        self.tree_title = QLabel("  大纲")
        self.tree_title.setStyleSheet(f"color:{C['text2']};font-size:12px;font-weight:600;padding:4px 0;")
        th.addWidget(self.tree_title); th.addStretch()
        self.tree_count = QLabel("0 节")
        self.tree_count.setStyleSheet(f"color:{C['text2']};font-size:11px;")
        th.addWidget(self.tree_count)

        tree_widget = QWidget()
        tl = QVBoxLayout(tree_widget); tl.setContentsMargins(0,0,0,0); tl.setSpacing(0)
        tl.addWidget(tree_header)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(lambda i,_: self._on_tree_click(i))
        tl.addWidget(self.tree)
        mid.addWidget(tree_widget)

        # 输出区
        output_widget = QWidget()
        ol = QVBoxLayout(output_widget); ol.setContentsMargins(0,0,0,0); ol.setSpacing(0)

        out_header = QWidget()
        oh = QHBoxLayout(out_header); oh.setContentsMargins(0,0,0,0)
        self.out_title = QLabel("  输出")
        self.out_title.setStyleSheet(f"color:{C['text2']};font-size:12px;font-weight:600;padding:4px 0;")
        oh.addWidget(self.out_title); oh.addStretch()
        self.out_status = QLabel("")
        self.out_status.setStyleSheet(f"color:{C['yellow']};font-size:11px;")
        oh.addWidget(self.out_status)
        ol.addWidget(out_header)

        self.content = QTextEdit()
        self.content.setReadOnly(True)
        self.content.setFont(QFont("Microsoft YaHei", 13))
        self.content.setPlaceholderText("输出区 — AI 生成的内容将显示在这里")
        ol.addWidget(self.content)

        # 底部输入栏
        input_bar = QHBoxLayout()
        self.fb_input = QLineEdit()
        self.fb_input.setPlaceholderText("输入反馈意见后按 Enter...")
        self.fb_input.returnPressed.connect(self._send_feedback)
        input_bar.addWidget(self.fb_input)

        self.act_btn = QPushButton("▶ 执行")
        self.act_btn.clicked.connect(self._execute)
        self.act_btn.setCursor(Qt.PointingHandCursor)
        self.act_btn.setStyleSheet(f"""
            QPushButton{{background:{C['accent']};color:#fff;border:none;border-radius:6px;
            padding:8px 24px;font-size:13px;font-weight:600;}}
            QPushButton:hover{{background:{C['accent2']};}}
            QPushButton:disabled{{background:{C['surface2']};color:{C['text2']};}}
        """)
        input_bar.addWidget(self.act_btn)
        ol.addLayout(input_bar)

        mid.addWidget(output_widget)
        mid.setSizes([200, 550])
        split.addWidget(mid)

        # ====== 右侧: 角色/世界观 ======
        right = QTabWidget()
        self.char_view = QTextBrowser()
        right.addTab(self.char_view, "👥 角色")
        self.world_view = QTextBrowser()
        right.addTab(self.world_view, "🌍 世界观")
        split.addWidget(right)

        split.setSizes([280, 800, 280])
        self.setCentralWidget(split)
        self.setStyleSheet(STYLE)


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
    # 项目管理
    # ================================================================
    def _scan_projects(self) -> list[dict]:
        """扫描 output/novels/ 下所有已有项目"""
        import glob
        # 用绝对路径，不受工作目录影响
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        novels_dir = os.path.join(base, "output", "novels")
        projects = []
        pattern = os.path.join(novels_dir, "*", "novel.db")
        for db_path in glob.glob(pattern):
            pid = os.path.basename(os.path.dirname(db_path))
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT title, genre, total_words, status FROM novels WHERE id=?", (pid,)).fetchone()
                conn.close()
                if row:
                    projects.append({"id": pid, "title": row[0], "genre": row[1], "words": row[2], "status": row[3]})
            except: pass
        return projects

    def _show_project_dialog(self, projects: list[dict]):
        """启动时显示已有项目列表，可选新建或继续"""
        msg = QDialog(self)
        msg.setWindowTitle("选择项目")
        msg.setFixedSize(500, 400)
        msg.setStyleSheet(f"background:{C['bg']};color:{C['text']};")

        layout = QVBoxLayout(msg)
        layout.addWidget(QLabel(f"<h2 style='color:{C['accent']}'>📖 已有项目</h2>"))

        lst = QListWidget()
        lst.setStyleSheet(f"QListWidget{{background:{C['surface']};border:1px solid {C['border']};border-radius:8px;font-size:14px;}} QListWidget::item{{padding:10px;}}")
        for p in projects:
            item = QListWidgetItem(f"  📖 {p['title']}  ·  {p['genre']}  ·  {p['words']:,}字  ·  {p['status']}")
            item.setData(Qt.UserRole, p["id"])
            lst.addItem(item)

        new_item = QListWidgetItem(f"  🆕  新建项目")
        new_item.setData(Qt.UserRole, "__new__")
        lst.addItem(new_item)
        lst.setCurrentRow(len(projects))  # 默认选新建
        layout.addWidget(lst)

        btn_row = QHBoxLayout()
        ok = QPushButton("  确  定  ")
        ok.clicked.connect(msg.accept)
        ok.setStyleSheet(f"background:{C['accent']};color:#fff;padding:10px 30px;border-radius:8px;font-weight:bold;")
        cancel = QPushButton("  取  消  ")
        cancel.clicked.connect(msg.reject)
        cancel.setStyleSheet(f"background:{C['surface2']};color:{C['text']};padding:10px 30px;border-radius:8px;")
        btn_row.addStretch(); btn_row.addWidget(cancel); btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        if msg.exec_() == QDialog.Accepted and lst.currentItem():
            pid = lst.currentItem().data(Qt.UserRole)
            if pid == "__new__":
                self._status("就绪 — 输入故事想法开始创作")
            else:
                self._load_project(pid)

    def _load_project(self, pid: str):
        """加载已有项目"""
        self.repo = NovelRepository(pid)
        project = self.repo.conn.execute("SELECT * FROM novels WHERE id=?", (pid,)).fetchone()
        if not project:
            self._status("❌ 项目加载失败"); return

        # 恢复构思数据
        chars = self.repo.conn.execute("SELECT * FROM characters WHERE novel_id=?", (pid,)).fetchall()
        bible = self.repo.conn.execute("SELECT * FROM story_bible WHERE project_id=?", (pid,)).fetchall()

        self._idea_data = {
            "title": project["title"], "genre": project["genre"],
            "premise": project["premise"],
            "world_building": bible[0]["value"] if bible else "",
            "characters": [{"name": c["name"], "role": c["role"], "traits": c["traits"]} for c in chars],
        }

        self.project_label.setText(f"  📖 {project['title']}")
        self.char_view.setText("\n".join(f"{c['name']}({c['role']}): {c['traits']}" for c in chars))
        self.world_view.setText(bible[0]["value"] if bible else "")

        # 恢复大纲树
        self.tree.clear()
        data = self.repo.get_outline_tree()
        nodes_by_pid = {}
        for n in data:
            nodes_by_pid.setdefault(n.get("parent_id") or 0, []).append(n)

        def build(parent, pid):
            for n in nodes_by_pid.get(pid, []):
                icon = {"volume":"📘","chapter":"📄","section":"📝"}.get(n["level"],"")
                done = "✅ " if n["status"] == "done" else ""
                item = QTreeWidgetItem(parent or self.tree, [f"{done}{icon} {n['title']}"])
                item.setData(0, Qt.UserRole, n["id"])
                if n["status"] == "done": item.setForeground(0, QColor(C["green"]))
                build(item, n["id"])

        for r in nodes_by_pid.get(0, []): build(None, r["id"])
        self.tree.expandAll()

        # 恢复进度
        p = self.repo.get_progress()
        self.tree_count.setText(f"{p['total_sections']} 节")
        self.progress_bar.setValue(int(p.get("progress_pct", 0)))
        self.progress_label.setText(f"{p['done_sections']}/{p['total_sections']} 节")
        self._status(f"✅ 已加载: {project['title']} — {p['total_words']:,} 字")

        self._mode = "write"
        self.tab_write.setChecked(True)
        self.info_stack.setCurrentIndex(2)
        self.out_title.setText(f"  📖 {project['title']}")
    def _switch_mode(self, idx):
        modes = ["idea", "outline", "write"]
        self._mode = modes[idx]
        self.info_stack.setCurrentIndex(idx)
        labels = ["💡 构思模式 — 输入想法扩展为创作方案",
                  "📋 大纲模式 — 规划章节结构",
                  "✍️ 写作模式 — 点击左侧大纲开始写作"]
        self._status(labels[idx])

    def _execute(self):
        if self._mode == "idea": self._llm("idea")
        elif self._mode == "outline": self._llm("outline")
        elif self._mode == "write": self._llm("write")

    def _llm(self, mode_tag):
        if mode_tag == "idea":
            idea = self.idea_input.toPlainText().strip()
            if not idea: return
            self.content.clear()
            self.out_status.setText("⏳ 生成中...")
            self.idea_btn.setEnabled(False)
            self.thread = LLMThread(self.cfg, PROMPTS["idea"], f"故事想法: {idea}")
            self.thread.chunk.connect(self._on_chunk)
            self.thread.done.connect(lambda r: (self._on_idea_result(r), self.idea_btn.setEnabled(True), self.out_status.setText("")))
            self.thread.error.connect(lambda e: (self.content.setPlainText(f"❌ {e}"), self.idea_btn.setEnabled(True)))

        elif mode_tag == "outline":
            if not self._idea_data: self.content.setPlainText("请先在构思模式生成故事设定"); return
            self.content.clear()
            self.out_status.setText("⏳ 生成中...")
            self.outline_btn.setEnabled(False)
            vols = self.vol_in.text() or "3"; chs = self.ch_in.text() or "4"
            user = f"已有设定:\n{json.dumps(self._idea_data, ensure_ascii=False)}\n\n请规划约{vols}卷每卷约{chs}章的大纲。"
            self.thread = LLMThread(self.cfg, PROMPTS["outline"], user)
            self.thread.chunk.connect(self._on_chunk)
            self.thread.done.connect(lambda r: (self._on_outline_result(r), self.outline_btn.setEnabled(True), self.out_status.setText("")))
            self.thread.error.connect(lambda e: (self.content.setPlainText(f"❌ {e}"), self.outline_btn.setEnabled(True)))

        elif mode_tag == "write":
            if not self.repo or not self._current_node_id:
                self.content.setPlainText("请先生成大纲，然后点击左侧大纲某一节"); return
            self.content.clear()
            self.out_status.setText("✍️ 写作中...")
            self.act_btn.setEnabled(False)
            ctx = self.repo.get_writing_context(self._current_node_id)
            self.ctx_label.setText(f"🧠 ~{ctx['token_estimate']} tokens | "
                                   f"角色{len(ctx.get('characters',[]))} | 伏笔{len(ctx.get('threads',[]))}")
            self.ctx_label.show()
            node = self.repo.get_node(self._current_node_id)
            fb = self.fb_input.text().strip(); self.fb_input.clear()
            user = f"{ctx['context_text']}\n\n---\n大纲: {node['title']}\n{'反馈: '+fb if fb else ''}\n请写本节:"
            self.thread = LLMThread(self.cfg, PROMPTS["write"], user)
            self.thread.chunk.connect(self._on_chunk)
            self.thread.done.connect(lambda r: (self._on_write_result(r), self.act_btn.setEnabled(True), self.out_status.setText("✅ 完成")))
            self.thread.error.connect(lambda e: (self.content.setPlainText(f"❌ {e}"), self.act_btn.setEnabled(True)))
        self.thread.start()

    def _on_chunk(self, text):
        c = self.content.textCursor(); c.movePosition(QTextCursor.End); c.insertText(text)
        self.content.ensureCursorVisible()

    # ================================================================
    # 结果处理
    # ================================================================
    def _on_idea_result(self, raw):
        data = self._parse_json(raw); self._idea_data = data
        chars = "\n".join(f"  {c['name']}({c.get('role','')}): {c.get('traits','')}" for c in data.get("characters", []))
        self.content.setHtml(f"""
        <h2 style='color:{C['accent']}'>{data.get('title','未命名')}</h2>
        <p><b>{data.get('genre','')}</b> · 看点: {data.get('hook','')}</p>
        <blockquote style='color:{C['text2']};border-left:3px solid {C['accent']};padding-left:12px;'>{data.get('premise','')}</blockquote>
        <h3>🌍 世界观</h3><p>{data.get('world_building','')}</p>
        <h3>👥 角色</h3><pre>{chars}</pre>
        """)
        self.char_view.setText(chars)
        self.world_view.setText(data.get('world_building',''))
        self.project_label.setText(f"  📖 {data.get('title','未命名')}")
        self._status("✅ 构思完成 — 切换到大纲模式继续")
        if not self.repo: self._init_db(data)

    def _on_outline_result(self, raw):
        data = self._parse_json(raw)
        self.tree.clear()
        if not self.repo: self._init_db(self._idea_data)
        self.repo.conn.execute("DELETE FROM outline_nodes WHERE novel_id=?", (self.repo.novel_id,))
        sort = 0; total_sections = 0
        for v_idx, vol in enumerate(data.get("volumes", []), 1):
            vid = self._add_db_node(None, "volume", sort, f"第{v_idx}卷 {vol.get('title','')}", ""); sort += 1
            vol_item = QTreeWidgetItem(self.tree, [f"📘 第{v_idx}卷 {vol.get('title','')}"])
            vol_item.setData(0, Qt.UserRole, vid)
            for c_idx, ch in enumerate(vol.get("chapters", []), 1):
                cid = self._add_db_node(vid, "chapter", sort, f"第{c_idx}章 {ch.get('title','')}", ch.get("summary","")); sort += 1
                ch_item = QTreeWidgetItem(vol_item, [f"📄 第{c_idx}章 {ch.get('title','')}"])
                ch_item.setData(0, Qt.UserRole, cid)
                for s_idx in range(ch.get("sections", 3)):
                    sid = self._add_db_node(cid, "section", sort, f"第{s_idx+1}节", ""); sort += 1; total_sections += 1
                    QTreeWidgetItem(ch_item, [f"📝 第{s_idx+1}节"]).setData(0, Qt.UserRole, sid)
                ch_item.setExpanded(True)
            vol_item.setExpanded(True)
        self.repo.conn.commit()
        self.tree_count.setText(f"{total_sections} 节")
        self._status("✅ 大纲完成 — 切换到写作模式，点击左侧开始")

    def _on_write_result(self, raw):
        if self.repo and self._current_node_id:
            m = re.search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)', raw)
            self.repo.save_section(self._current_node_id, raw, m.group(1) if m else "")
            self.repo.update_node_status(self._current_node_id, "done")
            self._refresh_tree_status()
            p = self.repo.get_progress()
            self.progress_bar.setValue(int(p.get("progress_pct", 0)))
            self.progress_label.setText(f"{p['done_sections']}/{p['total_sections']} 节")
            self._status(f"✅ 本节完成 — {p['total_words']:,} 字")

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
            if node: self._status(f"已选: {node['title']}")

    def _refresh_tree_status(self):
        if not self.repo: return
        data = self.repo.get_outline_tree()
        def update(item):
            nid = item.data(0, Qt.UserRole)
            if nid:
                node = next((n for n in data if n["id"] == nid), None)
                if node and node["status"] == "done":
                    item.setForeground(0, QColor(C["green"]))
            for i in range(item.childCount()): update(item.child(i))
        for i in range(self.tree.topLevelItemCount()): update(self.tree.topLevelItem(i))

    def _send_feedback(self):
        if self._mode == "write": self._llm("write")

    def _parse_json(self, raw):
        try:
            js = raw
            if "```json" in js: js = js.split("```json")[1].split("```")[0]
            elif "```" in js: js = js.split("```")[1].split("```")[0]
            return json.loads(js.strip())
        except: return {}

    def _status(self, msg): self.statusBar().showMessage(f"  {msg}")

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
