"""
AI 小说家 — 桌面编辑器 v4
==========================
三模式：构思 → 大纲 → 写作
右侧面板：当前内容 / 角色 / 世界观 / 全文
"""
import sys, os, re, json, time, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import PyQt5
_qd = os.path.dirname(PyQt5.__file__)
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_qd, "Qt5", "plugins", "platforms")
_bin = os.path.join(_qd, "Qt5", "bin")
if os.path.exists(_bin):
    os.environ["PATH"] = _bin + ";" + os.environ.get("PATH", "")

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QColor, QKeySequence

from config import load_config
from src.models.llm_client import chat_stream, chat
from src.db.novel_repository import NovelRepository
from src.desktop.theme import (
    C, sidebar_btn_style, accent_btn_style, input_style,
    text_edit_style, panel_style, body_style, global_scrollbar_style,
    tab_style, tree_style, list_widget_style, small_btn_style,
)
from src.desktop.prompts import IDEA_PROMPT, OUTLINE_PROMPT, WRITE_PROMPT, REVISE_PROMPT, REVIEW_PROMPT
from src.desktop.utils import (
    clean_output, parse_json_response, count_words,
    build_full_novel, build_full_html, get_volume_context,
)


# ═══════════════════════════════════════════════ 调试工具 ═══════════════════════════════════════════════
def _print_prompt(label: str, system: str, user: str):
    """打印发送给模型的 system + user prompt 到终端"""
    bar = "=" * 60
    sys_preview = system[:300].replace('\n', '\n  ')
    print(f"\n{bar}")
    print(f"📤 [{label}] → 模型: system_prompt ({len(system)}字符)")
    print(f"{bar}")
    print(f"  {sys_preview}...")
    print(f"--- user_prompt ({len(user)}字符) ---")
    print(f"  {user.replace(chr(10), chr(10) + '  ')}")
    print(f"{bar}\n", flush=True)


# ═══════════════════════════════════════════════ 流式线程 ═══════════════════════════════════════════════
class StreamThread(QThread):
    """LLM 流式调用线程，避免阻塞 UI"""
    chunk = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, cfg, system_prompt, user_prompt, label=""):
        super().__init__()
        self.cfg = cfg
        self.sys = system_prompt
        self.usr = user_prompt
        self.label = label  # "构思" / "大纲" / "写作" / "修订"

    def run(self):
        try:
            _print_prompt(self.label, self.sys, self.usr)
            buf = []
            chat_stream(self.cfg, self.sys, self.usr,
                        on_chunk=lambda t: (buf.append(t), self.chunk.emit(t)))
            self.done.emit("".join(buf))
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════════ 角色编辑弹窗 ═══════════════════════════════════════════════
class CharacterDialog(QDialog):
    """添加/编辑角色弹窗"""

    def __init__(self, parent=None, data: dict = None):
        super().__init__(parent)
        self.setWindowTitle("编辑角色" if data else "添加角色")
        self.setFixedSize(380, 420)
        self.setStyleSheet(f"background:{C['panel']};color:{C['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        fields = [
            ("name", "角色名", data.get("name", "") if data else ""),
            ("role", "身份（主角/配角/反派）", data.get("role", "") if data else ""),
            ("traits", "性格特征", data.get("traits", "") if data else ""),
            ("desire", "欲望（想要什么）", data.get("desire", "") if data else ""),
            ("fear", "恐惧（怕什么）", data.get("fear", "") if data else ""),
        ]
        self.inputs = {}

        for key, label, default in fields:
            layout.addWidget(QLabel(f"<span style='color:{C['muted']}'>{label}</span>"))
            inp = QLineEdit(default)
            inp.setStyleSheet(input_style())
            layout.addWidget(inp)
            self.inputs[key] = inp

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        cancel.setStyleSheet(small_btn_style())
        btn_row.addWidget(cancel)
        save = QPushButton("保存")
        save.clicked.connect(self.accept)
        save.setStyleSheet(accent_btn_style())
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

    def get_data(self) -> dict:
        return {k: v.text().strip() for k, v in self.inputs.items()}


# ═══════════════════════════════════════════════ 导出弹窗 ═══════════════════════════════════════════════
class ExportDialog(QDialog):
    """导出选项弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出小说")
        self.setFixedSize(360, 200)
        self.setStyleSheet(f"background:{C['panel']};color:{C['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(QLabel(f"<h3 style='color:{C['accent']}'>📥 导出格式</h3>"))

        self.fmt_txt = QRadioButton("纯文本 (.txt)")
        self.fmt_html = QRadioButton("网页 (.html)")
        self.fmt_txt.setChecked(True)
        for rb in [self.fmt_txt, self.fmt_html]:
            rb.setStyleSheet(f"color:{C['text']};font-size:14px;padding:4px;")
            layout.addWidget(rb)

        layout.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        cancel.setStyleSheet(small_btn_style())
        btn_row.addWidget(cancel)
        export = QPushButton("导出")
        export.clicked.connect(self.accept)
        export.setStyleSheet(accent_btn_style())
        btn_row.addWidget(export)
        layout.addLayout(btn_row)

    def get_format(self) -> str:
        return "html" if self.fmt_html.isChecked() else "txt"


# ═══════════════════════════════════════════════ 重命名弹窗 ═══════════════════════════════════════════════
class RenameDialog(QDialog):
    """大纲节点重命名"""

    def __init__(self, parent=None, title=""):
        super().__init__(parent)
        self.setWindowTitle("重命名")
        self.setFixedSize(350, 120)
        self.setStyleSheet(f"background:{C['panel']};color:{C['text']};")

        layout = QVBoxLayout(self)
        self.inp = QLineEdit(title)
        self.inp.setStyleSheet(input_style())
        self.inp.selectAll()
        layout.addWidget(self.inp)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        cancel.setStyleSheet(small_btn_style())
        btn_row.addWidget(cancel)
        ok = QPushButton("确定")
        ok.clicked.connect(self.accept)
        ok.setStyleSheet(accent_btn_style())
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)


# ═══════════════════════════════════════════════ 主窗口 ═══════════════════════════════════════════════
def _sanitize_title(raw: str, label: str, max_len: int = 15, strip_prefix: bool = True) -> str:
    """清洗模型返回的标题：去冗余前缀、截断过长内容。
    
    Args:
        raw: 原始标题文本
        label: 标签（卷/章/节），用于警告信息
        max_len: 最大允许长度
        strip_prefix: 是否去掉AI自己加的"第X卷/章"前缀（新数据用True，旧数据展示用False）
    """
    t = raw.strip()
    import re as _re
    
    # 去掉冗余的"第X卷"/"第X章"前缀（循环去掉叠多层的情况，如"第1卷 第一卷：火种觉醒"）
    if strip_prefix:
        is_vol = label in ("volume", "卷")
        is_ch = label in ("chapter", "章")
        is_sec = label in ("section", "节")
        if is_vol:
            while _re.match(r'^第[一二三四五六七八九十\d]+卷[：:\s]*', t):
                t = _re.sub(r'^第[一二三四五六七八九十\d]+卷[：:\s]*', '', t)
        elif is_ch:
            while _re.match(r'^第[一二三四五六七八九十\d]+章[：:\s]*', t):
                t = _re.sub(r'^第[一二三四五六七八九十\d]+章[：:\s]*', '', t)
        elif is_sec:
            while _re.match(r'^第[一二三四五六七八九十\d]+节[：:\s]*', t):
                t = _re.sub(r'^第[一二三四五六七八九十\d]+节[：:\s]*', '', t)
    
    # 去掉常见分隔符后的拼接内容（v/V 夹在中文中间必为拼接）
    for sep in [' v ', ' V ', 'v', 'V']:
        idx = t.find(sep)
        if idx > 2:  # 分隔符不在开头，且前面有中文
            before = t[:idx].strip()
            # 确认前面是中文结尾、后面也是中文（排除英文单词中的v）
            if _re.search(r'[\u4e00-\u9fff]$', before) and _re.search(r'^[\u4e00-\u9fff]', t[idx+len(sep):]):
                print(f"  ⚠️ [{label}标题检测到拼接] 在'{sep}'处截断: {t[:30]}...")
                t = before
                break
    
    if len(t) > max_len:
        print(f"  ⚠️ [{label}标题过长({len(t)}字)] 已截断: {t[:20]}... → {t[:max_len]}")
        t = t[:max_len]
    
    return t if t else f"未命名{label}"


# ═══════════════════════════════════════════════ 主窗口 ═══════════════════════════════════════════════
class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 小说家")
        self.resize(1320, 850)
        self.cfg = load_config()
        self.repo = None
        self._mode = "idea"
        self._idea = {}
        self._nid = None
        self._th = None
        self._search_visible = False

        self._ui()
        self._status("扫描已有项目...")
        projects = self._scan()
        if projects:
            self._dialog(projects)
        else:
            self._status("就绪 — 输入故事想法开始创作")

    # ═══════════════════════════════════════════ UI 构建 ═══════════════════════════════════════════
    def _ui(self):
        body = QWidget()
        body.setStyleSheet(body_style())
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ── 左边栏 ──
        sidebar = self._build_sidebar()
        h.addWidget(sidebar)

        # ── 中央（大纲树 + 执行栏 + 搜索）──
        center = self._build_center()
        h.addWidget(center)

        # ── 右边栏 ──
        right = self._build_right_panel()

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setSizes([650, 350])
        splitter.setStyleSheet(f"QSplitter::handle{{background:{C['border']};width:2px;}}")
        h.addWidget(splitter)
        self.setCentralWidget(body)

        # 全局滚动条
        self.setStyleSheet(global_scrollbar_style())

    def _build_sidebar(self) -> QWidget:
        """构建左侧边栏"""
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(panel_style())
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(16, 20, 16, 16)
        sl.setSpacing(4)

        # Logo
        logo = QLabel("AI 小说家")
        logo.setStyleSheet(f"font-size:16px;font-weight:800;color:{C['accent']};padding-bottom:12px;")
        sl.addWidget(logo)

        # 项目名
        self.proj_lbl = QLabel("未打开项目")
        self.proj_lbl.setStyleSheet(f"font-size:11px;color:{C['muted']};padding-bottom:16px;")
        sl.addWidget(self.proj_lbl)

        # 模式按钮
        sl.addWidget(QLabel(f"<span style='color:{C['muted']};font-size:10px;'>模式</span>"))
        self.btns = []
        for i, (icon, label) in enumerate([("💡", "构思"), ("📋", "大纲"), ("✍️", "写作"), ("🔍", "审稿")]):
            b = QPushButton(f"  {icon}  {label}")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, x=i: self._mode_switch(x))
            b.setStyleSheet(sidebar_btn_style())
            self.btns.append(b)
            sl.addWidget(b)
        self.btns[0].setChecked(True)

        sl.addSpacing(12)

        # 模式面板栈
        self.stack = QStackedWidget()
        self._build_idea_panel()
        self._build_outline_panel()
        self._build_write_panel()
        self._build_review_panel()
        sl.addWidget(self.stack)

        sl.addStretch()

        # 导出按钮
        export_btn = QPushButton("  📥  导出小说")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_dialog)
        export_btn.setStyleSheet(small_btn_style())
        sl.addWidget(export_btn)

        # 模型选择
        sl.addWidget(QLabel(f"<span style='color:{C['muted']};font-size:10px;'>模型</span>"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["deepseek-v4-pro", "deepseek-v4-flash"])
        self.model_combo.setCurrentText(self.cfg.get("model", "deepseek-v4-pro"))
        self.model_combo.currentTextChanged.connect(self._on_model_change)
        self.model_combo.setStyleSheet(f"""
            QComboBox{{background:{C['card']};color:{C['text']};border:1px solid {C['border']};
            border-radius:6px;padding:6px 10px;font-size:11px;}}
            QComboBox::drop-down{{border:none;}}
        """)
        sl.addWidget(self.model_combo)

        return sidebar

    def _build_idea_panel(self):
        """构思面板"""
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(4, 0, 4, 0)
        self.idea_in = QTextEdit()
        self.idea_in.setPlaceholderText("输入故事想法...")
        self.idea_in.setMaximumHeight(80)
        self.idea_in.setStyleSheet(input_style())
        l.addWidget(self.idea_in)
        btn = QPushButton("生成构思")
        btn.clicked.connect(lambda: self._go("idea"))
        btn.setStyleSheet(accent_btn_style())
        l.addWidget(btn)
        l.addStretch()
        self.stack.addWidget(p)

    def _build_outline_panel(self):
        """大纲面板"""
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(4, 0, 4, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel(f"<span style='color:{C['muted']}'>卷</span>"))
        self.v_in = QLineEdit("3")
        self.v_in.setFixedWidth(40)
        self.v_in.setStyleSheet(input_style())
        row.addWidget(self.v_in)
        row.addWidget(QLabel(f"<span style='color:{C['muted']}'>章/卷</span>"))
        self.c_in = QLineEdit("4")
        self.c_in.setFixedWidth(40)
        self.c_in.setStyleSheet(input_style())
        row.addWidget(self.c_in)
        row.addStretch()
        l.addLayout(row)

        btn = QPushButton("生成大纲")
        btn.clicked.connect(lambda: self._go("outline"))
        btn.setStyleSheet(accent_btn_style())
        l.addWidget(btn)
        # 批量替换
        replace_btn = QPushButton("批量替换")
        replace_btn.clicked.connect(self._batch_replace_outline)
        replace_btn.setStyleSheet(small_btn_style())
        l.addWidget(replace_btn)
        l.addStretch()
        self.stack.addWidget(p)

    def _build_write_panel(self):
        """写作面板"""
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(4, 0, 4, 0)

        self.prog_lbl = QLabel("未开始")
        self.prog_lbl.setStyleSheet(f"font-size:16px;font-weight:700;color:{C['green']};")
        l.addWidget(self.prog_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setStyleSheet(
            f"QProgressBar{{background:{C['card']};height:4px;border-radius:2px;}}"
            f"QProgressBar::chunk{{background:{C['green']};border-radius:2px;}}"
        )
        l.addWidget(self.prog_bar)

        self.ctx_lbl = QLabel("")
        self.ctx_lbl.setWordWrap(True)
        self.ctx_lbl.setStyleSheet(
            f"background:{C['card']};color:{C['yellow']};padding:8px;border-radius:6px;font-size:11px;"
        )
        self.ctx_lbl.hide()
        l.addWidget(self.ctx_lbl)
        l.addStretch()
        self.stack.addWidget(p)

    def _build_review_panel(self):
        """审稿面板"""
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(4, 0, 4, 0)
        tip = QLabel(f"<span style='color:{C['muted']};font-size:11px;'>对照大纲检查全文，找出差异和连贯性问题</span>")
        tip.setWordWrap(True)
        l.addWidget(tip)
        btn = QPushButton("开始审稿")
        btn.clicked.connect(lambda: self._go("review"))
        btn.setStyleSheet(accent_btn_style())
        l.addWidget(btn)
        l.addStretch()
        self.stack.addWidget(p)

    def _build_center(self) -> QWidget:
        """构建中央区域（大纲树 + 搜索 + 执行栏）"""
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # 大纲树
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setStyleSheet(tree_style())
        self.tree.itemClicked.connect(lambda i, _: self._tree_click(i))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        cl.addWidget(self.tree)

        # 搜索栏（默认隐藏）
        self.search_bar = QWidget()
        self.search_bar.hide()
        slayout = QHBoxLayout(self.search_bar)
        slayout.setContentsMargins(8, 4, 8, 4)
        self.search_in = QLineEdit()
        self.search_in.setPlaceholderText("搜索正文...")
        self.search_in.setStyleSheet(input_style())
        self.search_in.textChanged.connect(self._do_search)
        slayout.addWidget(self.search_in)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self._toggle_search)
        close_btn.setStyleSheet(f"background:transparent;color:{C['muted']};border:none;font-size:14px;")
        slayout.addWidget(close_btn)
        cl.addWidget(self.search_bar)

        # 反馈 + 执行栏
        bar = QHBoxLayout()
        self.fb_in = QLineEdit()
        self.fb_in.setPlaceholderText("修改意见 (Ctrl+Enter 执行)...")
        self.fb_in.returnPressed.connect(lambda: self._go(self._mode))
        self.fb_in.setStyleSheet(input_style())
        bar.addWidget(self.fb_in)

        self.go_btn = QPushButton("执行")
        self.go_btn.clicked.connect(lambda: self._go(self._mode))
        self.go_btn.setStyleSheet(accent_btn_style())
        bar.addWidget(self.go_btn)

        self.edit_btn = QPushButton("✏ 编辑正文")
        self.edit_btn.setCheckable(True)
        self.edit_btn.clicked.connect(self._toggle_edit)
        self.edit_btn.setStyleSheet(small_btn_style())
        bar.addWidget(self.edit_btn)
        cl.addLayout(bar)

        return center

    def _build_right_panel(self) -> QTabWidget:
        """构建右侧标签面板"""
        self.right_tabs = QTabWidget()
        self.right_tabs.setStyleSheet(tab_style())

        # 当前内容 — QTextEdit 自带滚动条，不需要外层 QScrollArea
        self.detail_v = QTextEdit()
        self.detail_v.setReadOnly(True)
        self.detail_v.setStyleSheet(text_edit_style())
        self.detail_v.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.right_tabs.addTab(self.detail_v, "当前内容")

        # 角色（可编辑面板）
        self.right_tabs.addTab(self._build_character_tab(), "角色")

        # 世界观
        self.world_v = QTextEdit()
        self.world_v.setReadOnly(True)
        self.world_v.setStyleSheet(text_edit_style())
        self.world_v.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.right_tabs.addTab(self.world_v, "世界观")

        # 大纲（可编辑）
        self.outline_edit = QTextEdit()
        self.outline_edit.setStyleSheet(text_edit_style())
        self.outline_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.right_tabs.addTab(self.outline_edit, "大纲")

        # 全文预览
        self.fulltext_v = QTextEdit()
        self.fulltext_v.setReadOnly(True)
        self.fulltext_v.setStyleSheet(text_edit_style())
        self.fulltext_v.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.right_tabs.addTab(self.fulltext_v, "全文")

        # 标签切换
        self.right_tabs.currentChanged.connect(self._on_tab_changed)

        return self.right_tabs

    def _build_character_tab(self) -> QWidget:
        """构建可编辑的角色管理面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 角色列表
        self.char_list = QListWidget()
        self.char_list.setStyleSheet(list_widget_style())
        self.char_list.itemDoubleClicked.connect(self._edit_character)
        layout.addWidget(self.char_list)

        # 按钮行
        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ 添加")
        add_btn.clicked.connect(self._add_character)
        add_btn.setStyleSheet(small_btn_style())
        btn_row.addWidget(add_btn)

        edit_btn = QPushButton("✏ 编辑")
        edit_btn.clicked.connect(self._edit_character)
        edit_btn.setStyleSheet(small_btn_style())
        btn_row.addWidget(edit_btn)

        del_btn = QPushButton("🗑 删除")
        del_btn.clicked.connect(self._delete_character)
        del_btn.setStyleSheet(small_btn_style())
        btn_row.addWidget(del_btn)
        layout.addLayout(btn_row)

        return panel

    # ═══════════════════════════════════════════ 键盘快捷键 ═══════════════════════════════════════════
    def keyPressEvent(self, event):
        """全局键盘快捷键"""
        if event.modifiers() == Qt.ControlModifier:
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                # Ctrl+Enter → 执行
                self._go(self._mode)
                return
            elif event.key() == Qt.Key_F:
                # Ctrl+F → 搜索
                self._toggle_search()
                return
            elif event.key() == Qt.Key_E:
                # Ctrl+E → 导出
                self._export_dialog()
                return
        super().keyPressEvent(event)

    # ═══════════════════════════════════════════ 核心逻辑 ═══════════════════════════════════════════
    def _scan(self):
        """扫描已有项目"""
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        d = os.path.join(base, "output", "novels")
        projects = []
        for db_path in glob.glob(os.path.join(d, "*", "novel.db")):
            pid = os.path.basename(os.path.dirname(db_path))
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                r = conn.execute("SELECT title, genre, total_words, status FROM novels WHERE id=?", (pid,)).fetchone()
                conn.close()
                if r:
                    projects.append({
                        "id": pid, "title": r[0], "genre": r[1],
                        "words": r[2], "status": r[3]
                    })
            except Exception:
                pass
        return projects

    def _dialog(self, projects):
        """项目选择弹窗"""
        d = QDialog(self)
        d.setWindowTitle("打开项目")
        d.setFixedSize(420, 380)
        d.setStyleSheet(f"background:{C['panel']};color:{C['text']};")
        l = QVBoxLayout(d)
        l.addWidget(QLabel(f"<h3 style='color:{C['accent']}'>📖 已有项目</h3>"))
        lst = QListWidget()
        lst.setStyleSheet(list_widget_style())
        for p in projects:
            it = QListWidgetItem(f"📖 {p['title']}\n  {p['genre']} · {p['words']:,}字 · {p['status']}")
            it.setData(Qt.UserRole, p["id"])
            lst.addItem(it)
        ni = QListWidgetItem("🆕  新建项目")
        ni.setData(Qt.UserRole, "__new__")
        lst.addItem(ni)
        lst.setCurrentRow(len(projects))
        l.addWidget(lst)

        br = QHBoxLayout()
        br.addStretch()
        ok = QPushButton("确定")
        ok.clicked.connect(d.accept)
        ok.setStyleSheet(accent_btn_style())
        br.addWidget(ok)
        l.addLayout(br)

        if d.exec_() == QDialog.Accepted and lst.currentItem():
            pid = lst.currentItem().data(Qt.UserRole)
            if pid == "__new__":
                self._status("就绪 — 输入想法开始创作")
            else:
                self._load(pid)

    def _load(self, pid):
        """加载已有项目"""
        self.repo = NovelRepository(pid)
        r = self.repo.conn.execute("SELECT * FROM novels WHERE id=?", (pid,)).fetchone()
        if not r:
            self._status("加载失败")
            return

        chars = self.repo.conn.execute("SELECT * FROM characters WHERE novel_id=?", (pid,)).fetchall()
        bible = self.repo.conn.execute("SELECT * FROM story_bible WHERE project_id=?", (pid,)).fetchall()

        self._idea = {
            "title": r["title"], "genre": r["genre"], "premise": r["premise"],
            "world_building": bible[0]["value"] if bible else "",
            "characters": [
                {"name": c["name"], "role": c["role"], "traits": c["traits"],
                 "desire": c["desire"] if "desire" in c.keys() else "",
                 "fear": c["fear"] if "fear" in c.keys() else ""}
                for c in chars
            ],
        }
        self.proj_lbl.setText(f"📖 {r['title']}")
        self.world_v.setPlainText(bible[0]["value"] if bible else "")

        # 刷新角色列表
        self._refresh_characters()

        # 展示构思
        self._show_idea()

        # 构建大纲树
        self._rebuild_tree()

        # 更新进度
        p = self.repo.get_progress()
        self.prog_bar.setValue(int(p.get("progress_pct", 0)))
        self.prog_lbl.setText(f"{p['done_sections']}/{p['total_sections']}节 · {p['total_words']:,}字")
        self._status(f"已加载: {r['title']} — {p['total_words']:,}字")

        # 切换到写作模式
        self._mode_switch(2)

    def _show_idea(self):
        """在右侧展示构思内容"""
        d = self._idea
        chars = "\n".join(
            f"{c['name']}({c.get('role', '')}): {c.get('traits', '')}"
            for c in d.get("characters", [])
        )
        html = f"""
        <h2 style='color:{C["accent"]}'>{d.get('title', '')}</h2>
        <p style='color:{C["muted"]}'>{d.get('genre', '')} · {d.get('hook', '')}</p>
        <blockquote style='color:{C["text"]};border-left:3px solid {C["accent"]};padding-left:12px;'>
          {d.get('premise', '')}
        </blockquote>
        <h3 style='color:{C["muted"]}'>世界观</h3><p>{d.get('world_building', '')}</p>
        <h3 style='color:{C["muted"]}'>角色</h3><pre style='color:{C["text"]}'>{chars}</pre>"""
        self.detail_v.setHtml(html)
        self.right_tabs.setCurrentIndex(0)
        self.idea_in.setPlainText(d.get('premise', ''))

    def _mode_switch(self, idx):
        """切换模式"""
        modes = ["idea", "outline", "write", "review"]
        self._mode = modes[idx]
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.btns):
            b.setChecked(i == idx)

        # 切换到写作模式时更新进度
        if idx == 2 and self.repo:
            p = self.repo.get_progress()
            self.prog_bar.setValue(int(p.get("progress_pct", 0)))
            self.prog_lbl.setText(f"{p['done_sections']}/{p['total_sections']}节 · {p['total_words']:,}字")

        # 切换到审稿模式时展示最新报告
        if idx == 3 and self.repo:
            last = self.repo.get_latest_review()
            if last:
                self.detail_v.setPlainText(last)
                self.right_tabs.setCurrentIndex(0)

    def _tree_click(self, item):
        """大纲树节点点击——展示对应内容"""
        nid = item.data(0, Qt.UserRole)
        if nid is None or not self.repo:
            return

        if nid == -1:
            # 卷或章节点（不可选），展示其下所有节的结构
            # 从 item text 提取标识
            text = item.text(0)
            self.detail_v.setHtml(f"<h3 style='color:{C['accent']}'>{text}</h3>"
                                  f"<p style='color:{C['muted']}'>点击下方节标题开始写作</p>")
            return

        # 节节点：有真实的 DB id
        self._nid = nid
        row = self.repo.conn.execute(
            "SELECT volume_title, chapter_title, section_order, section_title, summary, status "
            "FROM outline_nodes WHERE id=?",
            (nid,)
        ).fetchone()
        if not row:
            return

        # 同一章下所有节
        sibs = self.repo.conn.execute(
            "SELECT id, section_order, section_title, summary, status "
            "FROM outline_nodes WHERE novel_id=? AND volume_title=? AND chapter_title=? "
            "ORDER BY section_order",
            (self.repo.novel_id, row["volume_title"], row["chapter_title"])
        ).fetchall()

        if sibs:
            lines = [
                f"<h3 style='color:{C['accent']}'>{row['chapter_title']}</h3>",
                f"<p style='color:{C['muted']}'>{row['volume_title']}</p>",
            ]
            # 当前节概要
            if row["summary"]:
                lines.append(
                    f"<blockquote style='color:{C['yellow']};border-left:3px solid {C['yellow']};"
                    f"padding:6px 12px;margin:8px 0;font-size:13px;'>"
                    f"📌 本节概要：{row['summary']}</blockquote>"
                )
            lines.append("<hr>")
            for s in sibs:
                done = "✓" if s["status"] == "done" else "○"
                color = C['green'] if s["status"] == "done" else C['muted']
                marker = " ← 当前" if s["id"] == nid else ""
                lines.append(
                    f"<p style='color:{color}'>"
                    f"{done} 第{s['section_order']}节 {s['section_title']}: {s['summary'] or ''}{marker}"
                    f"</p>"
                )
            self.detail_v.setHtml("".join(lines))
            self.right_tabs.setCurrentIndex(0)
            self._status(f"已选: {row['section_title']} ({len(sibs)}节)")

        # 如果已写完，展示内容
        if row["status"] == "done":
            sec = self.repo.conn.execute(
                "SELECT content, word_count FROM sections WHERE outline_node_id=? ORDER BY id DESC LIMIT 1",
                (nid,)
            ).fetchone()
            if sec:
                summary_html = ""
                if row["summary"]:
                    summary_html = (
                        f"<blockquote style='color:{C['yellow']};border-left:3px solid {C['yellow']};"
                        f"padding:6px 12px;margin:8px 0;font-size:13px;'>"
                        f"📌 本节概要：{row['summary']}</blockquote>"
                    )
                self.detail_v.setHtml(
                    f"<h3 style='color:{C['accent']}'>{row['section_title']}</h3>"
                    f"<p style='color:{C['muted']}'>"
                    f"{row['volume_title']} · {row['chapter_title']} · {sec['word_count']}字</p>"
                    f"{summary_html}"
                    f"<hr><pre style='color:{C['text']};white-space:pre-wrap;'>{sec['content']}</pre>"
                )

        # 自动切换到写作模式
        self._mode_switch(2)

    # ═══════════════════════════════════════════ 三模式执行 ═══════════════════════════════════════════
    def _go(self, tag):
        """执行当前模式"""
        self._th = None
        fb = self.fb_in.text().strip()

        if tag == "idea":
            self._go_idea(fb)
        elif tag == "outline":
            self._go_outline(fb)
        elif tag == "write":
            self._go_write(fb)
        elif tag == "review":
            self._go_review()

        self.fb_in.clear()

    def _go_idea(self, fb):
        """构思模式"""
        if self._idea and fb:
            # 有反馈 → 修改现有构思，无需确认
            pass
        elif self.repo:
            # 已有项目 → 重新生成构思会覆盖角色/世界观，确认一下
            reply = QMessageBox.question(
                self, "确认重新生成构思",
                "当前项目已有构思和角色设定，重新生成将覆盖这些内容。\n\n确定继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                self._status("已取消构思生成")
                return

        self.detail_v.clear()
        self._status("生成中...")
        self.go_btn.setEnabled(False)

        if self._idea and fb:
            user_prompt = (
                f"现有设定:\n{json.dumps(self._idea, ensure_ascii=False)}\n\n"
                f"修改建议: {fb}\n\n请根据建议修改，返回完整JSON。"
            )
        else:
            idea = self.idea_in.toPlainText().strip()
            if not idea:
                self._status("请输入故事想法")
                self.go_btn.setEnabled(True)
                return
            user_prompt = f"故事想法: {idea}"

        self._th = StreamThread(self.cfg, IDEA_PROMPT, user_prompt, label="构思")
        self._th.chunk.connect(self._chunk)
        self._th.done.connect(self._idea_done)
        self._th.error.connect(lambda e: self._on_error("构思", e))
        self._th.start()

    def _go_outline(self, fb):
        """大纲模式"""
        if not self._idea:
            self._status("请先生成构思")
            self.go_btn.setEnabled(True)
            return

        self.detail_v.clear()
        self._status("生成中...")
        self.go_btn.setEnabled(False)

        # 注入角色+世界观约束
        ctx_parts = [json.dumps(self._idea, ensure_ascii=False)]
        chars = self._idea.get("characters", [])
        if chars:
            ctx_parts.append(
                "角色设定(大纲必须严格匹配):\n" +
                "\n".join(f"- {c['name']}({c.get('role', '')}): {c.get('traits', '')}" for c in chars)
            )
        wb = self._idea.get("world_building", "")
        if wb:
            ctx_parts.append(f"世界观约束: {wb}")
        ctx_text = "\n\n".join(ctx_parts)

        v = self.v_in.text() or "3"
        c = self.c_in.text() or "4"
        fb_prefix = f"修改建议: {fb}\n\n" if fb else ""
        user_prompt = f"{ctx_text}\n\n{fb_prefix}请规划约{v}卷×{c}章的大纲。返回完整JSON。"

        self._th = StreamThread(self.cfg, OUTLINE_PROMPT, user_prompt, label="大纲")
        self._th.chunk.connect(self._chunk)
        self._th.done.connect(self._out_done)
        self._th.error.connect(lambda e: self._on_error("大纲", e))
        self._th.start()

    def _go_write(self, fb):
        """写作模式——使用流式 + thinking 过滤"""
        if not self.repo or not self._nid:
            self.detail_v.setPlainText("请先生成大纲，点击左侧某一节")
            self.go_btn.setEnabled(True)
            return

        self.detail_v.clear()
        self._status("写作中...")
        self.go_btn.setEnabled(False)

        ctx = self.repo.get_writing_context(self._nid)
        self._status(f"上下文 ~{ctx['token_estimate']} tokens")

        n = self.repo.get_node(self._nid)
        if not n:
            self._status("节点不存在")
            self.go_btn.setEnabled(True)
            return

        sec_title = n.get("section_title") or n.get("title", "")
        chap_ctx = self._build_chapter_context(self._nid)

        # 构建 chapter 大纲
        chap_outline = f"【大纲】\n{chap_ctx}\n当前节：{sec_title}" if chap_ctx else f"【大纲】\n当前节：{sec_title}"

        # 当前卷所有已写内容（1M 上下文绰绰有余，整卷发过去）
        vol_ctx = get_volume_context(self.repo, self._nid)
        recap_block = f"【前情提要】\n{vol_ctx}\n" if vol_ctx else ""

        # 角色+世界观上下文
        context_block = ctx['context_text'] if ctx.get('context_text') else ""

        if fb and n.get("status") == "done":
            sec = self.repo.conn.execute(
                "SELECT content FROM sections WHERE outline_node_id=? ORDER BY id DESC LIMIT 1",
                (self._nid,)
            ).fetchone()
            if sec:
                user_prompt = (
                    f"{chap_outline}\n\n"
                    f"{recap_block}"
                    f"{context_block}\n\n"
                    f"【原文】\n{sec['content']}\n\n"
                    f"【修改意见】\n{fb}"
                )
                prompt_to_use = REVISE_PROMPT
            else:
                user_prompt = (
                    f"{chap_outline}\n\n"
                    f"{recap_block}"
                    f"{context_block}\n\n"
                    f"【修改意见】\n{fb}"
                )
                prompt_to_use = WRITE_PROMPT
        elif fb and n.get("status") != "done":
            user_prompt = (
                f"{chap_outline}\n\n"
                f"{recap_block}"
                f"{context_block}\n\n"
                f"【修改意见】\n{fb}"
            )
            prompt_to_use = WRITE_PROMPT
        else:
            user_prompt = (
                f"{chap_outline}\n\n"
                f"{recap_block}"
                f"{context_block}"
            )
            prompt_to_use = WRITE_PROMPT

        # 流式写入（chat_stream 已内置 thinking 块过滤）
        write_label = "修订" if prompt_to_use == REVISE_PROMPT else "写作"
        self._stream_buf = []
        self._th = StreamThread(self.cfg, prompt_to_use, user_prompt, label=write_label)
        self._th.chunk.connect(self._chunk)
        self._th.done.connect(self._write_done)
        self._th.error.connect(lambda e: self._on_error("写作", e))
        self._th.start()

    def _go_review(self):
        """审稿模式：全文对照大纲检查"""
        if not self.repo:
            self._status("请先打开项目")
            return

        # 先展示上次审稿报告
        last = self.repo.get_latest_review()
        if last:
            self.detail_v.setPlainText(last)

        self.detail_v.clear()
        self.right_tabs.setCurrentIndex(0)
        self._status("审稿中...")
        self.go_btn.setEnabled(False)

        # 构建大纲摘要
        outline_lines = ["【大纲】"]
        for r in self.repo.conn.execute(
            "SELECT volume_title, chapter_title, section_order, section_title, summary, status "
            "FROM outline_nodes WHERE novel_id=? AND section_title != '' ORDER BY sort_order",
            (self.repo.novel_id,)
        ).fetchall():
            status = "✓" if r["status"] == "done" else "○"
            outline_lines.append(
                f"{status} {r['volume_title']} > {r['chapter_title']} > "
                f"第{r['section_order']}节「{r['section_title']}」: {r['summary'] or '(无概要)'}"
            )
        outline_text = "\n".join(outline_lines)

        from src.desktop.utils import build_full_novel
        full_text = build_full_novel(self.repo)

        user_prompt = f"{outline_text}\n\n---\n\n【正文】\n{full_text}\n\n---\n\n请对照大纲审稿，输出审稿报告。"

        def on_done(raw):
            self.go_btn.setEnabled(True)
            self._status("审稿完成")
            self.repo.save_review(raw)

        self._th = StreamThread(self.cfg, REVIEW_PROMPT, user_prompt, label="审稿")
        self._th.chunk.connect(self._chunk)
        self._th.done.connect(on_done)
        self._th.error.connect(lambda e: self._on_error("审稿", e))
        self._th.start()

    def _build_chapter_context(self, nid: int) -> str:
        """构建当前节的整章结构上下文（使用新平铺列）"""
        row = self.repo.conn.execute(
            "SELECT volume_title, chapter_title FROM outline_nodes WHERE id=?", (nid,)
        ).fetchone()
        if not row:
            return ""

        sibs = self.repo.conn.execute(
            "SELECT section_order, section_title, summary, status FROM outline_nodes "
            "WHERE novel_id=? AND volume_title=? AND chapter_title=? ORDER BY section_order",
            (self.repo.novel_id, row["volume_title"], row["chapter_title"])
        ).fetchall()
        if not sibs:
            return ""

        lines = ["\n## 本章结构"]
        for s in sibs:
            done = "✓" if s["status"] == "done" else "○"
            lines.append(
                f"- {done} 第{s['section_order']}节 {s['section_title']}: {s['summary'] or ''}"
            )
        return "\n".join(lines)

    def _chunk(self, t):
        """流式文本追加"""
        c = self.detail_v.textCursor()
        c.movePosition(QTextCursor.End)
        c.insertText(t)
        self.detail_v.ensureCursorVisible()

    def _on_error(self, stage, err):
        """统一错误处理"""
        self.go_btn.setEnabled(True)
        self._status("")
        QMessageBox.warning(self, f"{stage}失败", f"错误信息:\n{err}")

    # ═══════════════════════════════════════════ 构思完成 ═══════════════════════════════════════════
    def _idea_done(self, raw):
        self.go_btn.setEnabled(True)
        self._status("")

        d, err = parse_json_response(raw)
        if err:
            QMessageBox.warning(self, "构思解析失败", err)
            self.detail_v.setPlainText(f"原始返回:\n{raw[:500]}")
            return

        self._idea = d
        chars = "\n".join(
            f"{c['name']}({c.get('role', '')}): {c.get('traits', '')}"
            for c in d.get("characters", [])
        )
        html = f"""
        <h2 style='color:{C["accent"]}'>{d.get('title', '')}</h2>
        <p style='color:{C["muted"]}'>{d.get('genre', '')} · {d.get('hook', '')}</p>
        <blockquote style='color:{C["text"]};border-left:3px solid {C["accent"]};padding-left:12px;'>
          {d.get('premise', '')}
        </blockquote>
        <h3>世界观</h3><p>{d.get('world_building', '')}</p>
        <h3>角色</h3><pre>{chars}</pre>"""
        self.detail_v.setHtml(html)
        self.world_v.setPlainText(d.get('world_building', ''))
        self.proj_lbl.setText(f"📖 {d.get('title', '')}")

        # 刷新角色列表
        self._refresh_characters()

        if not self.repo:
            self._init_db(d)

        self._status("构思完成 — 切换到大纲模式")

    # ═══════════════════════════════════════════ 大纲完成 ═══════════════════════════════════════════
    def _out_done(self, raw):
        self.go_btn.setEnabled(True)
        self._status("")

        d, err = parse_json_response(raw)
        if not d.get("volumes"):
            # 流式返回不完整或解析失败，用非流式 fallback
            reason = err or "流式返回缺少 volumes 字段"
            self._status(f"流式不完整({reason[:30]}…)，正在用非流式重试...")
            try:
                fallback_prompt = (
                    f"已有设定:\n{json.dumps(self._idea, ensure_ascii=False)}\n"
                    f"规划{self.v_in.text() or '3'}卷×{self.c_in.text() or '4'}章"
                )
                _print_prompt("大纲(非流式fallback)", OUTLINE_PROMPT, fallback_prompt)
                fallback_raw = chat(self.cfg, OUTLINE_PROMPT, fallback_prompt)
                d, err2 = parse_json_response(fallback_raw)
                if err2:
                    QMessageBox.warning(self, "大纲解析失败",
                        f"流式原因: {reason}\n非流式原因: {err2}\n\n请重试或调整卷章数量。")
                    return
            except Exception as e:
                QMessageBox.warning(self, "大纲生成失败", f"非流式重试也失败了:\n{e}")
                return

        if not d.get("volumes"):
            QMessageBox.warning(self, "大纲生成失败", "未能生成有效的大纲结构，请重试")
            self.go_btn.setEnabled(True)
            return

        # 检查 volumes 是否为空数组
        total_volumes = len(d["volumes"])
        total_chapters = sum(len(v.get("chapters", [])) for v in d["volumes"])
        if total_volumes == 0 or total_chapters == 0:
            QMessageBox.warning(self, "大纲生成失败",
                f"大纲结构无效：{total_volumes}卷 {total_chapters}章，请重试")
            self.go_btn.setEnabled(True)
            return

        if not self.repo:
            self._init_db(self._idea)

        # 检查是否已有大纲 → 提示用户确认
        existing = self.repo.conn.execute(
            "SELECT COUNT(*) FROM outline_nodes WHERE novel_id=?", (self.repo.novel_id,)
        ).fetchone()[0]
        if existing > 0:
            done_count = self.repo.conn.execute(
                "SELECT COUNT(*) FROM outline_nodes WHERE novel_id=? AND status='done'",
                (self.repo.novel_id,)
            ).fetchone()[0]
            msg = f"当前已有 {existing} 个大纲节点"
            if done_count > 0:
                msg += f"（其中 {done_count} 节已写完）"
            msg += "，重新生成将清空所有大纲。\n\n确定继续？"
            reply = QMessageBox.question(self, "确认重新生成大纲", msg,
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                self._status("已取消大纲生成")
                return

        # 清除旧大纲 + 关联的 sections（避免孤儿数据）
        old_nodes = self.repo.conn.execute(
            "SELECT id FROM outline_nodes WHERE novel_id=?", (self.repo.novel_id,)
        ).fetchall()
        for node in old_nodes:
            self.repo.conn.execute("DELETE FROM sections WHERE outline_node_id=?", (node["id"],))
        self.repo.conn.execute("DELETE FROM outline_nodes WHERE novel_id=?", (self.repo.novel_id,))
        self.repo.conn.commit()
        self.tree.clear()
        total = 0
        global_ch = 1  # 全局章节计数器，跨卷顺延

        for vi, vol in enumerate(d.get("volumes", []), 1):
            vol_title_raw = _sanitize_title(vol.get('title', ''), "卷", 15, strip_prefix=True) or f"第{vi}卷"
            # 存干净名，展示时动态加编号
            vol_db = vol_title_raw

            for ch in vol.get("chapters", []):
                ch_title_raw = _sanitize_title(ch.get('title', ''), "章", 15, strip_prefix=True) or f"第{global_ch}章"
                ch_db = ch_title_raw
                ch_summary = ch.get("summary", "")
                global_ch += 1

                # 卷节点（首次出现时创建）
                vol_item = QTreeWidgetItem(self.tree, [f"📘 第{vi}卷 {vol_title_raw}"])
                vol_item.setData(0, Qt.UserRole, -1)
                vol_item.setFlags(vol_item.flags() & ~Qt.ItemIsSelectable)

                # 章节点（全局章节编号）
                ch_display = f"第{global_ch-1}章 {ch_title_raw}" if ch_title_raw else f"第{global_ch-1}章"
                ch_item = QTreeWidgetItem(vol_item, [f"📄 {ch_display}"])
                ch_item.setData(0, Qt.UserRole, -1)
                ch_item.setToolTip(0, ch_summary)

                secs = ch.get("sections", [])
                if isinstance(secs, list):
                    for si, sec in enumerate(secs):
                        if isinstance(sec, dict):
                            stitle = _sanitize_title(sec.get("title", f"第{si+1}节"), "节", 12, strip_prefix=True)
                            ssum = sec.get("summary", "")
                        else:
                            stitle = _sanitize_title(str(sec), "节", 12, strip_prefix=True) if sec else f"第{si+1}节"
                            ssum = ""
                        # 写入数据库（存干净名）
                        sid = self._add_section(vol_db, ch_db, si + 1, stitle, ssum)
                        total += 1
                        sec_item = QTreeWidgetItem(ch_item, [f"📝 {stitle}"])
                        sec_item.setData(0, Qt.UserRole, sid)
                else:
                    for si in range(secs if isinstance(secs, int) else 3):
                        sid = self._add_section(vol_db, ch_db, si + 1, f"第{si+1}节", "")
                        total += 1
                        sec_item = QTreeWidgetItem(ch_item, [f"📝 第{si+1}节"])
                        sec_item.setData(0, Qt.UserRole, sid)

                ch_item.setExpanded(True)
            vol_item.setExpanded(True)

        self.repo.conn.commit()
        self._status("大纲完成 — 切换到写作模式")

    # ═══════════════════════════════════════════ 写作完成 ═══════════════════════════════════════════
    def _write_done(self, raw):
        self.go_btn.setEnabled(True)
        self._status("")

        clean = clean_output(raw)

        if self.repo and self._nid:
            # 提取摘要 + 清除摘要标记
            m = re.search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)', clean)
            summary = m.group(1) if m else ""
            clean_body = re.sub(r'【本节摘要】[：:]\s*.+?(?:\n|$)', '', clean).strip()
            self.detail_v.setPlainText(clean_body)

            self.repo.save_section(self._nid, clean_body, summary)
            self.repo.update_node_status(self._nid, "done")
            self._refresh_tree()
            self._refresh_characters()

            p = self.repo.get_progress()
            self.prog_bar.setValue(int(p.get("progress_pct", 0)))
            self.prog_lbl.setText(f"{p['done_sections']}/{p['total_sections']}节 · {p['total_words']:,}字")
            self._status(f"完成 — {p['total_words']:,}字")
        else:
            # 无 repo 时直接展示原始清洗结果
            self.detail_v.setPlainText(clean)

    def _init_db(self, d):
        """初始化数据库"""
        self.repo = NovelRepository(f"novel_{int(time.time())}")
        n = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.repo.conn.execute(
            "INSERT INTO novels VALUES(?,?,?,?,?,?,?,?)",
            (self.repo.novel_id, d.get("title", ""), d.get("genre", ""),
             d.get("premise", ""), "draft", 0, n, n)
        )
        for c in d.get("characters", []):
            self.repo.conn.execute(
                "INSERT INTO characters(novel_id,name,role,traits,desire,fear,arc,updated_at) VALUES(?,?,?,?,?,?,?)",
                (self.repo.novel_id, c["name"], c.get("role", ""), c.get("traits", ""),
                 c.get("desire", ""), c.get("fear", ""), "", n)
            )
        self.repo.conn.execute(
            "INSERT INTO story_bible(project_id,category,key,value,source_scene,updated_at) VALUES(?,?,?,?,?,?)",
            (self.repo.novel_id, "world_rule", "世界观", d.get("world_building", ""), 0, n)
        )
        self.repo.conn.commit()

    def _add_section(self, vol_title, ch_title, sec_order, sec_title, summary):
        """添加一节到数据库"""
        # 计算 sort_order（基于已有最大 sort_order + 1）
        max_sort = self.repo.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM outline_nodes WHERE novel_id=?",
            (self.repo.novel_id,)
        ).fetchone()[0]
        self.repo.conn.execute(
            """INSERT INTO outline_nodes
               (novel_id, volume_title, chapter_title, section_order, section_title, summary, status, sort_order)
               VALUES (?,?,?,?,?,?,?,?)""",
            (self.repo.novel_id, vol_title, ch_title, sec_order, sec_title, summary, "pending", max_sort + 1)
        )
        return self.repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _rebuild_tree(self):
        """从数据库重建大纲树（使用平铺列）"""
        self.tree.clear()
        if not self.repo:
            return

        # 先尝试新列，回退到旧结构
        rows = self.repo.conn.execute(
            "SELECT id, volume_title, chapter_title, section_order, section_title, summary, status "
            "FROM outline_nodes WHERE novel_id=? AND section_title != '' "
            "ORDER BY sort_order",
            (self.repo.novel_id,)
        ).fetchall()

        if not rows:
            # 旧数据：尝试迁移后再查
            self.repo._migrate_outline()
            rows = self.repo.conn.execute(
                "SELECT id, volume_title, chapter_title, section_order, section_title, summary, status "
                "FROM outline_nodes WHERE novel_id=? AND section_title != '' "
                "ORDER BY sort_order",
                (self.repo.novel_id,)
            ).fetchall()

        if not rows:
            return

        # 按卷→章分组构建树（带编号）
        vol_items = {}    # vol_title → (item, vol_num)
        ch_items = {}     # (vol_title, ch_title) → (item, ch_num)
        vol_counter = 0
        ch_counter = 0
        last_vol = None

        for r in rows:
            vt = r["volume_title"] or "未命名卷"
            ct = r["chapter_title"] or "未命名章"

            # 卷节点
            if vt != last_vol:
                last_vol = vt
                vol_counter += 1
                label = f"📘 第{vol_counter}卷 {vt}"
                item = QTreeWidgetItem(self.tree, [label])
                item.setData(0, Qt.UserRole, -1)
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                vol_items[vt] = (item, vol_counter)

            # 章节点
            key = (vt, ct)
            if key not in ch_items:
                ch_counter += 1
                label = f"📄 第{ch_counter}章 {ct}"
                item = QTreeWidgetItem(vol_items[vt][0], [label])
                item.setData(0, Qt.UserRole, -1)
                if r["summary"]:
                    item.setToolTip(0, r["summary"])
                ch_items[key] = (item, ch_counter)

            # 节节点
            done = "✓ " if r["status"] == "done" else ""
            label = f"{done}📝 {r['section_title']}" if r["section_title"] else f"第{r['section_order']}节"
            sec_item = QTreeWidgetItem(ch_items[key][0], [label])
            sec_item.setData(0, Qt.UserRole, r["id"])
            if r["status"] == "done":
                sec_item.setForeground(0, QColor(C["green"]))

        # 展开所有
        for v_item, _ in vol_items.values():
            v_item.setExpanded(True)
        for c_item, _ in ch_items.values():
            c_item.setExpanded(True)

    def _refresh_tree(self):
        """刷新大纲树的完成状态——简单重建"""
        self._rebuild_tree()

    # ═══════════════════════════════════════════ 角色管理 ═══════════════════════════════════════════
    def _refresh_characters(self):
        """刷新角色列表"""
        self.char_list.clear()
        if not self.repo:
            return

        for c in self._idea.get("characters", []):
            item = QListWidgetItem(f"{c['name']}  [{c.get('role', '未知')}]")
            tooltip = c.get('traits', '')
            if c.get('desire'):
                tooltip += f"\n欲望：{c['desire']}"
            if c.get('fear'):
                tooltip += f"\n恐惧：{c['fear']}"
            item.setToolTip(tooltip)
            item.setData(Qt.UserRole, c.get("name", ""))
            self.char_list.addItem(item)

    def _add_character(self):
        """添加角色"""
        dlg = CharacterDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "提示", "角色名不能为空")
                return
            self._idea.setdefault("characters", []).append(data)
            self._refresh_characters()
            self._persist_characters()
            self._status(f"已添加角色: {data['name']}")

    def _edit_character(self):
        """编辑角色"""
        item = self.char_list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一个角色")
            return
        name = item.data(Qt.UserRole)
        existing = next((c for c in self._idea.get("characters", []) if c["name"] == name), None)
        if not existing:
            return

        dlg = CharacterDialog(self, existing)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            existing.update(data)
            self._refresh_characters()
            self._persist_characters()
            self._status(f"已更新角色: {data['name']}")

    def _delete_character(self):
        """删除角色"""
        item = self.char_list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一个角色")
            return
        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除角色「{name}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._idea["characters"] = [
                c for c in self._idea.get("characters", []) if c["name"] != name
            ]
            self._refresh_characters()
            self._persist_characters()
            self._status(f"已删除角色: {name}")

    def _persist_characters(self):
        """将角色列表持久化到数据库"""
        if not self.repo:
            return
        # 清除旧数据
        self.repo.conn.execute("DELETE FROM characters WHERE novel_id=?", (self.repo.novel_id,))
        n = time.strftime("%Y-%m-%dT%H:%M:%S")
        for c in self._idea.get("characters", []):
            self.repo.conn.execute(
                "INSERT INTO characters(novel_id,name,role,traits,desire,fear,arc,updated_at) VALUES(?,?,?,?,?,?,?)",
                (self.repo.novel_id, c["name"], c.get("role", ""), c.get("traits", ""),
                 c.get("desire", ""), c.get("fear", ""), "", n)
            )
        self.repo.conn.commit()

    # ═══════════════════════════════════════════ 大纲树右键菜单 ═══════════════════════════════════════════
    def _tree_context_menu(self, pos):
        """大纲树右键菜单"""
        item = self.tree.itemAt(pos)
        if not item or not self.repo:
            return

        nid = item.data(0, Qt.UserRole)
        if nid == -1:
            return  # 卷/章节点不可操作

        node = self.repo.get_node(nid)
        if not node:
            return

        node_title = node.get("section_title") or ""

        menu = QMenu(self)
        menu.setStyleSheet(f"background:{C['panel']};color:{C['text']};border:1px solid {C['border']};")

        edit_title = menu.addAction("✏ 改节标题")
        edit_summary = menu.addAction("📝 改节概要")
        menu.addSeparator()

        toggle_label = "✓ 标记完成" if node["status"] != "done" else "○ 标记待写"
        toggle_action = menu.addAction(toggle_label)
        menu.addSeparator()

        delete_action = menu.addAction("🗑 删除此节")

        action = menu.exec_(self.tree.viewport().mapToGlobal(pos))

        if action == edit_title:
            self._rename_node(nid, node_title, "section_title")
        elif action == edit_summary:
            self._edit_node_summary(nid, node.get("summary", ""))
        elif action == toggle_action:
            new_status = "pending" if node["status"] == "done" else "done"
            self.repo.update_node_status(nid, new_status)
            self._rebuild_tree()
            self._status(f"已标记: {node_title}")
        elif action == delete_action:
            reply = QMessageBox.question(
                self, "确认删除", f"确定要删除「{node_title}」吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._delete_node_r(nid)
                self._rebuild_tree()
                self._status(f"已删除: {node_title}")

    def _rename_node(self, nid, old_title, col="section_title"):
        """重命名大纲节点"""
        dlg = RenameDialog(self, old_title)
        if dlg.exec_() == QDialog.Accepted:
            new_title = dlg.inp.text().strip()
            if new_title and new_title != old_title:
                self.repo.conn.execute(
                    f"UPDATE outline_nodes SET {col}=? WHERE id=?", (new_title, nid)
                )
                self.repo.conn.commit()
                self._rebuild_tree()
                self._status(f"已重命名: {old_title} → {new_title}")

    def _edit_node_summary(self, nid, old_summary):
        """编辑节概要"""
        dlg = RenameDialog(self, old_summary)
        dlg.setWindowTitle("编辑概要")
        if dlg.exec_() == QDialog.Accepted:
            new_summary = dlg.inp.text().strip()
            if new_summary != old_summary:
                self.repo.conn.execute(
                    "UPDATE outline_nodes SET summary=? WHERE id=?", (new_summary, nid)
                )
                self.repo.conn.commit()
                self._status("概要已更新")

    def _delete_node_r(self, nid):
        """删除大纲节点及其关联 sections"""
        self.repo.conn.execute("DELETE FROM sections WHERE outline_node_id=?", (nid,))
        self.repo.conn.execute("DELETE FROM outline_nodes WHERE id=?", (nid,))
        self.repo.conn.commit()

    def _batch_replace_outline(self):
        """批量替换大纲中的文本（如把角色名全部替换）"""
        if not self.repo:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("批量替换大纲")
        dlg.setFixedSize(380, 180)
        dlg.setStyleSheet(f"background:{C['panel']};color:{C['text']};")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)

        layout.addWidget(QLabel(f"<span style='color:{C['muted']}'>查找</span>"))
        find_in = QLineEdit()
        find_in.setStyleSheet(input_style())
        layout.addWidget(find_in)

        layout.addWidget(QLabel(f"<span style='color:{C['muted']}'>替换为</span>"))
        replace_in = QLineEdit()
        replace_in.setStyleSheet(input_style())
        layout.addWidget(replace_in)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        cancel.setStyleSheet(small_btn_style())
        btn_row.addWidget(cancel)
        ok = QPushButton("全部替换")
        ok.clicked.connect(dlg.accept)
        ok.setStyleSheet(accent_btn_style())
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        if dlg.exec_() == QDialog.Accepted:
            find_text = find_in.text().strip()
            replace_text = replace_in.text().strip()
            if not find_text:
                return

            # 替换 section_title 和 summary 中的文本
            updated = 0
            for col in ["section_title", "summary", "volume_title", "chapter_title"]:
                self.repo.conn.execute(
                    f"UPDATE outline_nodes SET {col} = REPLACE({col}, ?, ?) WHERE novel_id=?",
                    (find_text, replace_text, self.repo.novel_id)
                )
                updated += self.repo.conn.total_changes
            self.repo.conn.commit()
            self._rebuild_tree()
            QMessageBox.information(self, "完成", f"已替换 {updated} 处")

    # ═══════════════════════════════════════════ 搜索 ═══════════════════════════════════════════
    def _toggle_search(self):
        """切换搜索栏显示"""
        self._search_visible = not self._search_visible
        self.search_bar.setVisible(self._search_visible)
        if self._search_visible:
            self.search_in.setFocus()
        else:
            self.search_in.clear()
            self._restore_detail()

    def _do_search(self, text):
        """在当前内容中搜索并高亮"""
        if not text:
            self._restore_detail()
            return

        # 用 QTextEdit 的 find 功能
        cursor = self.detail_v.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.detail_v.setTextCursor(cursor)

        # 高亮所有匹配
        fmt = QTextEdit.ExtraSelection()
        fmt.format.setBackground(QColor("#e0af68"))
        fmt.format.setForeground(QColor("#000000"))

        extras = []
        doc = self.detail_v.document()
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(text, cursor)
            if cursor.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.format = fmt.format
            sel.cursor = cursor
            extras.append(sel)

        self.detail_v.setExtraSelections(extras)

    def _restore_detail(self):
        """清除搜索高亮"""
        self.detail_v.setExtraSelections([])

    # ═══════════════════════════════════════════ 导出 ═══════════════════════════════════════════
    def _export_dialog(self):
        """导出对话框"""
        if not self.repo:
            QMessageBox.information(self, "提示", "请先打开或创建一个项目")
            return

        dlg = ExportDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            fmt = dlg.get_format()
            self._do_export(fmt)

    def _do_export(self, fmt: str):
        """执行导出"""
        novel_info = self.repo.conn.execute(
            "SELECT title FROM novels WHERE id=?", (self.repo.novel_id,)
        ).fetchone()
        title = novel_info["title"] if novel_info else "未命名"

        # 选择保存路径
        ext = "html" if fmt == "html" else "txt"
        default_name = f"{title}.{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出小说", default_name,
            f"{'HTML' if fmt == 'html' else '文本'}文件 (*.{ext})"
        )
        if not path:
            return

        try:
            if fmt == "html":
                content = build_full_html(self.repo)
            else:
                content = build_full_novel(self.repo)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            QMessageBox.information(self, "导出成功", f"小说已导出到:\n{path}")
            self._status(f"已导出: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ═══════════════════════════════════════════ 全文预览 ═══════════════════════════════════════════
    def _on_tab_changed(self, idx):
        """标签页切换"""
        # 离开大纲标签时保存
        if hasattr(self, '_last_tab') and self._last_tab == 3:
            self._save_outline_if_dirty()
        self._last_tab = idx

        if idx == 3 and self.repo:
            self._load_outline_edit()
        elif idx == 4 and self.repo:
            self._show_fulltext()

    def _load_outline_edit(self):
        """加载大纲到可编辑文本框"""
        if not self.repo:
            return
        lines = []
        last_vol = None
        last_ch = None
        for r in self.repo.conn.execute(
            "SELECT volume_title, chapter_title, section_order, section_title, summary, status "
            "FROM outline_nodes WHERE novel_id=? AND section_title != '' ORDER BY sort_order",
            (self.repo.novel_id,)
        ).fetchall():
            if r["volume_title"] != last_vol:
                last_vol = r["volume_title"]
                last_ch = None
                lines.append(f"【{last_vol}】")
            if r["chapter_title"] != last_ch:
                last_ch = r["chapter_title"]
                lines.append(f"  【{last_ch}】")
            status = "✓" if r["status"] == "done" else "○"
            lines.append(f"    {status} 第{r['section_order']}节 | 标题：{r['section_title']} | 概要：{r['summary'] or ''}")
        self.outline_edit.setPlainText("\n".join(lines))

    def _save_outline_if_dirty(self):
        """如果大纲有修改则保存"""
        if not self.repo:
            return
        text = self.outline_edit.toPlainText()
        if not text.strip():
            return

        current_vol = ""
        current_ch = ""
        updated = 0
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 卷标记：【火种觉醒】
            vm = re.match(r'^【(.+)】$', line)
            if vm and not line.startswith('  '):
                current_vol = vm.group(1).strip()
                current_ch = ""
                continue
            # 章标记：  【废墟中的遗产】
            cm = re.match(r'^  【(.+)】$', line)
            if cm:
                current_ch = cm.group(1).strip()
                continue
            # 节行：    ○ 第1节 | 标题：xxx | 概要：xxx
            sm = re.match(r'\s*[✓○]\s*第(\d+)节\s*\|\s*标题[：:]\s*(.+?)\s*\|\s*概要[：:]\s*(.*)', line)
            if sm and current_vol and current_ch:
                sec_order = int(sm.group(1))
                new_title = sm.group(2).strip()
                new_summary = sm.group(3).strip()
                self.repo.conn.execute(
                    "UPDATE outline_nodes SET section_title=?, summary=? "
                    "WHERE novel_id=? AND volume_title=? AND chapter_title=? AND section_order=?",
                    (new_title, new_summary, self.repo.novel_id, current_vol, current_ch, sec_order)
                )
                updated += 1
        if updated > 0:
            self.repo.conn.commit()
            self._rebuild_tree()
            self._status(f"大纲已保存 ({updated} 节)")

    def _show_fulltext(self):
        """在全文标签中展示完整小说"""
        if not self.repo:
            self.fulltext_v.setPlainText("请先打开项目")
            return

        text = build_full_novel(self.repo)
        self.fulltext_v.setPlainText(text)

    def _status(self, m):
        """状态栏消息"""
        self.statusBar().showMessage(f"  {m}")

    def _on_model_change(self, model):
        """模型切换"""
        self.cfg["model"] = model
        self._status(f"已切换模型: {model}")

    def _toggle_edit(self):
        """切换正文编辑模式"""
        editing = self.edit_btn.isChecked()
        self.detail_v.setReadOnly(not editing)
        if editing:
            self.edit_btn.setText("💾 保存修改")
            self.edit_btn.setStyleSheet(f"QPushButton{{background:{C['yellow']};color:#000;border-radius:6px;padding:6px 12px;font-size:12px;}}")
        else:
            self.edit_btn.setText("✏ 编辑正文")
            self.edit_btn.setStyleSheet(small_btn_style())
            if self.repo and self._nid:
                new_content = self.detail_v.toPlainText()
                self.repo.conn.execute(
                    "UPDATE sections SET content=?, updated_at=? WHERE outline_node_id=? AND id="
                    "(SELECT id FROM sections WHERE outline_node_id=? ORDER BY id DESC LIMIT 1)",
                    (new_content, time.strftime("%Y-%m-%dT%H:%M:%S"), self._nid, self._nid)
                )
                self.repo.conn.commit()
                self._status("正文已保存")


# ═══════════════════════════════════════════════ 入口 ═══════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWin()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
