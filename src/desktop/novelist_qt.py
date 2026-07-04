"""
AI 小说家 — 桌面编辑器 v3
"""
import sys, os, re, json, time, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import PyQt5
_qd = os.path.dirname(PyQt5.__file__)
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_qd, "Qt5", "plugins", "platforms")
_bin = os.path.join(_qd, "Qt5", "bin")
if os.path.exists(_bin): os.environ["PATH"] = _bin + ";" + os.environ.get("PATH", "")

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtGui import QFont, QTextCursor, QColor, QPalette, QFontDatabase

from config import load_config
from src.models.llm_client import chat_stream
from src.db.novel_repository import NovelRepository

# ── 配色 ──
C = {
    "bg":       "#1a1b26",
    "panel":    "#24283b",
    "card":     "#1f2335",
    "border":   "#3b4261",
    "accent":   "#7aa2f7",
    "green":    "#9ece6a",
    "yellow":   "#e0af68",
    "red":      "#f7768e",
    "text":     "#c0caf5",
    "muted":    "#565f89",
    "white":    "#ffffff",
}

# ── 流式线程 ──
class StreamThread(QThread):
    chunk = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)
    def __init__(self, cfg, sys, usr): super().__init__(); self.c=cfg; self.s=sys; self.u=usr
    def run(self):
        try:
            buf=[]; chat_stream(self.c,self.s,self.u,on_chunk=lambda t:(buf.append(t),self.chunk.emit(t)))
            self.done.emit("".join(buf))
        except Exception as e: self.error.emit(str(e))

# ── 提示词 ──
P = {
    "idea":    "小说顾问。JSON:{title,premise,genre,hook,world_build,characters:[{name,role,traits}]}",
    "outline": "大纲策划。JSON:{volumes:[{title,chapters:[{title,summary,sections:[{title,summary}]}]}]}。每节8-12字概要。和已有角色世界观一致",
    "write":   "你是职业小说家。输出纯正文内容，不要JSON/大纲/章节标题。根据上下文写正文800-2000字。保持设定一致。末尾【本节摘要】一句话",
}

# ── 主窗口 ──
class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 小说家")
        self.resize(1280, 820)
        self.cfg = load_config()
        self.repo = None; self._mode = "idea"; self._idea = {}; self._nid = None

        self._ui()
        self._status("扫描已有项目...")
        projects = self._scan()
        if projects:
            self._dialog(projects)
        else:
            self._status("就绪 — 输入故事想法开始创作")

    # ═══════════════════════════════════════ UI ═══════════════════════════════════════
    def _ui(self):
        body = QWidget()
        body.setStyleSheet(f"background:{C['bg']};")
        h = QHBoxLayout(body); h.setContentsMargins(0,0,0,0); h.setSpacing(0)

        # ── 左边栏 ──
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(f"background:{C['panel']};")
        sl = QVBoxLayout(sidebar); sl.setContentsMargins(16,20,16,16); sl.setSpacing(4)

        logo = QLabel("AI 小说家")
        logo.setStyleSheet(f"font-size:16px;font-weight:800;color:{C['accent']};padding-bottom:12px;")
        sl.addWidget(logo)

        self.proj_lbl = QLabel("未打开项目")
        self.proj_lbl.setStyleSheet(f"font-size:11px;color:{C['muted']};padding-bottom:16px;")
        sl.addWidget(self.proj_lbl)

        sl.addWidget(QLabel(f"<span style='color:{C['muted']};font-size:10px;'>模式</span>"))
        self.btns = []
        for i,(icon,label) in enumerate([("💡","构思"),("📋","大纲"),("✍️","写作")]):
            b = QPushButton(f"  {icon}  {label}")
            b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _,x=i: self._mode_switch(x))
            b.setStyleSheet(f"""
                QPushButton{{background:transparent;color:{C['muted']};border:none;text-align:left;
                padding:10px 14px;font-size:13px;border-radius:8px;}}
                QPushButton:hover{{background:{C['card']};color:{C['text']};}}
                QPushButton:checked{{background:#2a3a5c;color:{C['accent']};font-weight:600;}}
            """)
            self.btns.append(b); sl.addWidget(b)
        self.btns[0].setChecked(True)

        sl.addSpacing(16)

        self.stack = QStackedWidget()
        # 构思面板
        p1=QWidget();l1=QVBoxLayout(p1);l1.setContentsMargins(4,0,4,0)
        self.idea_in = QTextEdit()
        self.idea_in.setPlaceholderText("输入故事想法...")
        self.idea_in.setMaximumHeight(80)
        self.idea_in.setStyleSheet(f"background:{C['card']};color:{C['text']};border:1px solid {C['border']};border-radius:8px;padding:10px;font-size:12px;")
        l1.addWidget(self.idea_in)
        b1=QPushButton("生成构思");b1.clicked.connect(lambda:self._go("idea"))
        b1.setStyleSheet(f"QPushButton{{background:{C['accent']};color:#000;border-radius:8px;padding:10px;font-weight:600;}}QPushButton:hover{{opacity:0.9;}}")
        l1.addWidget(b1);l1.addStretch();self.stack.addWidget(p1)

        # 大纲面板
        p2=QWidget();l2=QVBoxLayout(p2);l2.setContentsMargins(4,0,4,0)
        r=QHBoxLayout()
        r.addWidget(QLabel(f"<span style='color:{C['muted']}'>卷</span>"))
        self.v_in=QLineEdit("3");self.v_in.setFixedWidth(40);self.v_in.setStyleSheet(f"background:{C['card']};color:{C['text']};border:1px solid {C['border']};border-radius:6px;padding:6px;")
        r.addWidget(self.v_in)
        r.addWidget(QLabel(f"<span style='color:{C['muted']}'>章/卷</span>"))
        self.c_in=QLineEdit("4");self.c_in.setFixedWidth(40);self.c_in.setStyleSheet(self.v_in.styleSheet())
        r.addWidget(self.c_in);r.addStretch();l2.addLayout(r)
        b2=QPushButton("生成大纲");b2.clicked.connect(lambda:self._go("outline"));b2.setStyleSheet(b1.styleSheet())
        l2.addWidget(b2);l2.addStretch();self.stack.addWidget(p2)

        # 写作面板
        p3=QWidget();l3=QVBoxLayout(p3);l3.setContentsMargins(4,0,4,0)
        self.prog_lbl=QLabel("未开始");self.prog_lbl.setStyleSheet(f"font-size:16px;font-weight:700;color:{C['green']};")
        l3.addWidget(self.prog_lbl)
        self.prog_bar=QProgressBar();self.prog_bar.setTextVisible(False)
        self.prog_bar.setStyleSheet(f"QProgressBar{{background:{C['card']};height:4px;border-radius:2px;}}QProgressBar::chunk{{background:{C['green']};border-radius:2px;}}")
        l3.addWidget(self.prog_bar)
        self.ctx_lbl=QLabel("");self.ctx_lbl.setWordWrap(True)
        self.ctx_lbl.setStyleSheet(f"background:{C['card']};color:{C['yellow']};padding:8px;border-radius:6px;font-size:11px;")
        self.ctx_lbl.hide();l3.addWidget(self.ctx_lbl);l3.addStretch()
        self.stack.addWidget(p3)

        sl.addWidget(self.stack);sl.addStretch()
        info=QLabel(f"<span style='color:{C['muted']};font-size:10px;'>模型: {self.cfg['model']}</span>")
        info.setStyleSheet("padding-top:8px;");sl.addWidget(info)
        h.addWidget(sidebar)

        # ── 中央区域(大纲树) ──
        mid=QWidget();ml=QVBoxLayout(mid);ml.setContentsMargins(0,0,0,0)
        self.tree=QTreeWidget()
        self.tree.setHeaderHidden(True);self.tree.setIndentation(16)
        self.tree.setStyleSheet(f"""
            QTreeWidget{{background:transparent;color:{C['text']};border:none;font-size:13px;}}
            QTreeWidget::item{{padding:4px 8px;border-radius:4px;}}
            QTreeWidget::item:hover{{background:{C['card']};}}
            QTreeWidget::item:selected{{background:#2a3a5c;color:{C['accent']};}}
        """)
        self.tree.itemClicked.connect(lambda i,_:self._tree_click(i))
        ml.addWidget(self.tree)
        # 反馈+执行栏
        bar=QHBoxLayout()
        self.fb_in=QLineEdit();self.fb_in.setPlaceholderText("修改意见 (Enter 执行)...");self.fb_in.returnPressed.connect(lambda:self._go(self._mode))
        self.fb_in.setStyleSheet(f"background:{C['card']};color:{C['text']};border:1px solid {C['border']};border-radius:8px;padding:10px 14px;font-size:13px;")
        bar.addWidget(self.fb_in)
        self.go_btn=QPushButton("执行");self.go_btn.clicked.connect(lambda:self._go(self._mode))
        self.go_btn.setStyleSheet(f"QPushButton{{background:{C['accent']};color:#000;border-radius:8px;padding:10px 24px;font-weight:600;}}QPushButton:hover{{opacity:0.9;}}QPushButton:disabled{{background:{C['card']};color:{C['muted']};}}")
        bar.addWidget(self.go_btn)
        ml.addLayout(bar)
        h.addWidget(mid)

        # ── 右边栏 ──
        self.right_tabs=QTabWidget()
        self.right_tabs.setStyleSheet(f"""
            QTabWidget::pane{{background:{C['bg']};border:none;}}
            QTabBar::tab{{background:{C['panel']};color:{C['muted']};padding:8px 16px;font-size:12px;border:none;}}
            QTabBar::tab:selected{{color:{C['accent']};border-bottom:2px solid {C['accent']};}}
        """)
        self.detail_v=QTextBrowser();self.detail_v.setStyleSheet(f"background:transparent;color:{C['text']};border:none;padding:12px;font-size:13px;")
        self.right_tabs.addTab(self.detail_v,"当前内容")
        self.char_v=QTextBrowser();self.char_v.setStyleSheet(self.detail_v.styleSheet())
        self.right_tabs.addTab(self.char_v,"角色")
        self.world_v=QTextBrowser();self.world_v.setStyleSheet(self.detail_v.styleSheet())
        self.right_tabs.addTab(self.world_v,"世界观")
        
        # 中央+右侧之间可拖拽分割
        splitter=QSplitter(Qt.Horizontal)
        h.removeWidget(mid)
        splitter.addWidget(mid)
        splitter.addWidget(self.right_tabs)
        splitter.setSizes([600,280])
        splitter.setStyleSheet(f"QSplitter::handle{{background:{C['border']};width:2px;}}")
        h.addWidget(splitter)
        self.setCentralWidget(body)

    # ═══════════════════════════════════════ 逻辑 ═══════════════════════════════════════
    def _scan(self):
        base=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        d=os.path.join(base,"output","novels")
        projects=[]
        for db in glob.glob(os.path.join(d,"*","novel.db")):
            pid=os.path.basename(os.path.dirname(db))
            try:
                import sqlite3;conn=sqlite3.connect(db);conn.row_factory=sqlite3.Row
                r=conn.execute("SELECT title,genre,total_words,status FROM novels WHERE id=?",(pid,)).fetchone()
                conn.close()
                if r: projects.append({"id":pid,"title":r[0],"genre":r[1],"words":r[2],"status":r[3]})
            except: pass
        return projects

    def _dialog(self, projects):
        d=QDialog(self);d.setWindowTitle("打开项目");d.setFixedSize(420,380)
        d.setStyleSheet(f"background:{C['panel']};color:{C['text']};")
        l=QVBoxLayout(d)
        l.addWidget(QLabel(f"<h3 style='color:{C['accent']}'>📖 已有项目</h3>"))
        lst=QListWidget()
        lst.setStyleSheet(f"QListWidget{{background:{C['card']};border:1px solid {C['border']};border-radius:8px;font-size:14px;}}QListWidget::item{{padding:12px;border-bottom:1px solid {C['border']};}}QListWidget::item:hover{{background:{C['bg']};}}")
        for p in projects:
            it=QListWidgetItem(f"📖 {p['title']}\n  {p['genre']} · {p['words']:,}字 · {p['status']}")
            it.setData(Qt.UserRole,p["id"]);lst.addItem(it)
        ni=QListWidgetItem("🆕  新建项目");ni.setData(Qt.UserRole,"__new__");lst.addItem(ni)
        lst.setCurrentRow(len(projects));l.addWidget(lst)
        br=QHBoxLayout();br.addStretch()
        ok=QPushButton("确定");ok.clicked.connect(d.accept);ok.setStyleSheet(f"background:{C['accent']};color:#000;padding:8px 24px;border-radius:6px;font-weight:600;")
        br.addWidget(ok);l.addLayout(br)
        if d.exec_()==QDialog.Accepted and lst.currentItem():
            pid=lst.currentItem().data(Qt.UserRole)
            if pid=="__new__": self._status("就绪 — 输入想法开始创作")
            else: self._load(pid)

    def _load(self, pid):
        self.repo=NovelRepository(pid)
        r=self.repo.conn.execute("SELECT * FROM novels WHERE id=?",(pid,)).fetchone()
        if not r: self._status("加载失败");return
        chars=self.repo.conn.execute("SELECT * FROM characters WHERE novel_id=?",(pid,)).fetchall()
        bible=self.repo.conn.execute("SELECT * FROM story_bible WHERE project_id=?",(pid,)).fetchall()
        self._idea={"title":r["title"],"genre":r["genre"],"premise":r["premise"],
                    "world_building":bible[0]["value"] if bible else "",
                    "characters":[{"name":c["name"],"role":c["role"],"traits":c["traits"]} for c in chars]}
        self.proj_lbl.setText(f"📖 {r['title']}")
        self.char_v.setText("\n".join(f"{c['name']}({c['role']})\n  {c['traits']}" for c in chars))
        self.world_v.setText(bible[0]["value"] if bible else "")
        # 展示已有构思
        self._show_idea()
        # 大纲树
        self.tree.clear();data=self.repo.get_outline_tree()
        npm={}
        for n in data: npm.setdefault(n.get("parent_id") or 0,[]).append(n)
        def build(parent,pid):
            for n in npm.get(pid,[]):
                icon={"volume":"📘","chapter":"📄","section":"📝"}.get(n["level"],"")
                done="✓ " if n["status"]=="done" else ""
                it=QTreeWidgetItem(parent or self.tree,[f"{done}{icon} {n['title']}"])
                it.setData(0,Qt.UserRole,n["id"])
                if n["status"]=="done":it.setForeground(0,QColor(C["green"]))
                build(it,n["id"])
        for rx in npm.get(0,[]):build(None,rx["id"])
        self.tree.expandAll()
        p=self.repo.get_progress()
        self.prog_bar.setValue(int(p.get("progress_pct",0)))
        self.prog_lbl.setText(f"{p['done_sections']}/{p['total_sections']}节 · {p['total_words']:,}字")
        self._status(f"已加载: {r['title']} — {p['total_words']:,}字")
        self._mode_switch(2)

    def _show_idea(self):
        d=self._idea
        chars="\n".join(f"{c['name']}({c.get('role','')}): {c.get('traits','')}" for c in d.get("characters",[]))
        html=f"""
        <h2 style='color:{C["accent"]}'>{d.get('title','')}</h2>
        <p style='color:{C["muted"]}'>{d.get('genre','')} · {d.get('hook','')}</p>
        <blockquote style='color:{C["text"]};border-left:3px solid {C["accent"]};padding-left:12px;'>{d.get('premise','')}</blockquote>
        <h3 style='color:{C["muted"]}'>世界观</h3><p>{d.get('world_building','')}</p>
        <h3 style='color:{C["muted"]}'>角色</h3><pre style='color:{C["text"]}'>{chars}</pre>"""
        self.detail_v.setHtml(html)
        self.right_tabs.setCurrentIndex(0)
        self.idea_in.setPlainText(d.get('premise',''))

    def _mode_switch(self, idx):
        modes=["idea","outline","write"];self._mode=modes[idx]
        self.stack.setCurrentIndex(idx)
        for i,b in enumerate(self.btns):b.setChecked(i==idx)
        # 切换到写作模式时更新进度
        if idx==2 and self.repo:
            tree=self.repo.get_outline_tree()
            if tree:
                done=[n for n in tree if n.get("status")=="done"]
                total=len([n for n in tree if n.get("level")=="section"])
                self.prog_lbl.setText(f"{len(done)}/{total}节 · {self.repo.get_progress()['total_words']:,}字")
                self.prog_bar.setValue(int(len(done)/total*100) if total else 0)

    def _tree_click(self, item):
        nid=item.data(0,Qt.UserRole)
        if nid and self.repo:
            self._nid=nid
            node=self.repo.get_node(nid)
            if not node: return
            # 右侧"当前内容"展示
            level=node.get("level","")
            summary=node.get("summary","")
            title=node["title"]
            if level=="chapter":
                # 展示整章结构
                sibs=self.repo.conn.execute(
                    "SELECT title,summary,status FROM outline_nodes WHERE parent_id=? ORDER BY sort_order",
                    (nid,)).fetchall()
                if sibs:
                    lines=[f"<h3 style='color:{C['accent']}'>{title}</h3>"]
                    if summary: lines.append(f"<p style='color:{C['muted']}'>{summary}</p>")
                    lines.append("<hr>")
                    for i,s in enumerate(sibs):
                        done="✓" if s["status"]=="done" else "○"
                        color=C['green'] if s["status"]=="done" else C['muted']
                        lines.append(f"<p style='color:{color}'>{done} 第{i+1}节 {s['title']}: {s['summary'] or ''}</p>")
                    self.detail_v.setHtml("".join(lines))
                    self.right_tabs.setCurrentIndex(0)
                    self._status(f"已选: {title} ({len(sibs)}节)")
            elif level=="section" and node.get("status")=="done":
                sec=self.repo.conn.execute(
                    "SELECT content,word_count FROM sections WHERE outline_node_id=? ORDER BY id DESC LIMIT 1",
                    (nid,)).fetchone()
                if sec:
                    self.detail_v.setHtml(f"<h3 style='color:{C['accent']}'>{title}</h3><p style='color:{C['muted']}'>{sec['word_count']}字</p><hr><pre style='color:{C['text']};white-space:pre-wrap;'>{sec['content']}</pre>")
            elif summary:
                self.detail_v.setHtml(f"<h3 style='color:{C['accent']}'>{title}</h3><p style='color:{C['text']}'>{summary}</p>")
            else:
                self.detail_v.setHtml(f"<h3 style='color:{C['accent']}'>{title}</h3><p style='color:{C['muted']}'>待写作</p>")

    def _go(self, tag):
        fb=self.fb_in.text().strip()
        if tag=="idea":
            self.detail_v.clear();self._status("生成中...");self.go_btn.setEnabled(False)
            if self._idea and fb:
                u=f"现有设定:\n{json.dumps(self._idea,ensure_ascii=False)}\n\n修改建议: {fb}\n\n请根据建议修改，返回完整JSON。"
            else:
                idea=self.idea_in.toPlainText().strip()
                if not idea: self.go_btn.setEnabled(True);return
                u=f"故事想法: {idea}"
            self._th=StreamThread(self.cfg,P["idea"],u)
            self._th.chunk.connect(self._chunk)
            self._th.done.connect(self._idea_done)
        elif tag=="outline":
            if not self._idea: self.go_btn.setEnabled(True);return
            self.detail_v.clear();self._status("生成中...");self.go_btn.setEnabled(False)
            # 注入 Tier4: 角色+世界观
            ctx_parts=[json.dumps(self._idea,ensure_ascii=False)]
            chars=self._idea.get("characters",[])
            if chars:
                ctx_parts.append("角色设定(大纲必须严格匹配):\n"+"\n".join(
                    f"- {c['name']}({c.get('role','')}): {c.get('traits','')}" for c in chars))
            wb=self._idea.get("world_building","")
            if wb: ctx_parts.append(f"世界观约束: {wb}")
            ctx_text="\n\n".join(ctx_parts)
            v=self.v_in.text() or "3";c=self.c_in.text() or "4"
            fb_prefix=f"修改建议: {fb}\n\n" if fb else ""
            u=f"{ctx_text}\n\n{fb_prefix}请规划约{v}卷×{c}章的大纲。返回完整JSON。"
            self._th=StreamThread(self.cfg,P["outline"],u)
            self._th.chunk.connect(self._chunk)
            self._th.done.connect(self._out_done)
        elif tag=="write":
            if not self.repo or not self._nid: self.detail_v.setPlainText("请先生成大纲，点击左侧某一节");self.go_btn.setEnabled(True);return
            self.detail_v.clear();self._status("写作中...");self.go_btn.setEnabled(False)
            ctx=self.repo.get_writing_context(self._nid)
            self._status(f"上下文 ~{ctx['token_estimate']} tokens")
            n=self.repo.get_node(self._nid)
            # 构建整章上下文
            chap_ctx=""
            if n:
                parent_id=n.get("parent_id",0)
                siblings=self.repo.conn.execute(
                    "SELECT title,summary FROM outline_nodes WHERE parent_id=? ORDER BY sort_order",
                    (parent_id,)).fetchall()
                if siblings:
                    chap_ctx="\n## 本章结构\n"
                    for i,sib in enumerate(siblings):
                        marker="← 当前" if sib["title"]==n["title"] else ""
                        chap_ctx+=f"- 第{i+1}节 {sib['title']}: {sib['summary'] or ''} {marker}\n"
            fb=self.fb_in.text().strip();self.fb_in.clear()
            # 有反馈+已有内容 → 带原文一起发给模型
            if fb and n.get("status")=="done":
                sec=self.repo.conn.execute(
                    "SELECT content FROM sections WHERE outline_node_id=? ORDER BY id DESC LIMIT 1",
                    (self._nid,)).fetchone()
                if sec:
                    u=f"{ctx['context_text']}\n{chap_ctx}\n---\n已有内容:\n{sec['content'][:2000]}\n\n修改意见: {fb}\n\n请根据修改意见重写本节（纯小说内容）:"
                else:
                    u=f"{ctx['context_text']}\n{chap_ctx}\n---\n大纲: {n['title']}\n{fb}\n\n请写本节正文（纯小说内容）:"
            else:
                u=f"{ctx['context_text']}\n{chap_ctx}\n---\n大纲: {n['title']}\n{fb if fb else ''}\n\n请写本节正文（纯小说内容，不要JSON/大纲/章节标题）:"
            from src.models.llm_client import chat
            self.go_btn.setEnabled(False)
            self.detail_v.setPlainText("⏳ 生成中...")
            QApplication.processEvents()
            try:
                raw=chat(self.cfg,P["write"],u)
                self._write_done(raw)
            except Exception as e:
                self.detail_v.setPlainText(f"错误: {e}")
            self.go_btn.setEnabled(True);self._status("")
        self.fb_in.clear()
        self._th.error.connect(lambda e:(self.detail_v.setPlainText(f"错误: {e}"),self.go_btn.setEnabled(True)))
        self._th.start()

    def _chunk(self,t):
        c=self.detail_v.textCursor();c.movePosition(QTextCursor.End);c.insertText(t)
        self.detail_v.ensureCursorVisible()

    def _idea_done(self,raw):
        self.go_btn.setEnabled(True);self._status("")
        d=self._parse(raw);self._idea=d
        chars="\n".join(f"{c['name']}({c.get('role','')}): {c.get('traits','')}" for c in d.get("characters",[]))
        html=f"""
        <h2 style='color:{C["accent"]}'>{d.get('title','')}</h2>
        <p style='color:{C["muted"]}'>{d.get('genre','')} · {d.get('hook','')}</p>
        <blockquote style='color:{C["text"]};border-left:3px solid {C["accent"]};padding-left:12px;'>{d.get('premise','')}</blockquote>
        <h3>世界观</h3><p>{d.get('world_building','')}</p>
        <h3>角色</h3><pre>{chars}</pre>"""
        self.detail_v.setHtml(html)
        self.char_v.setText(chars);self.world_v.setText(d.get('world_building',''))
        self.proj_lbl.setText(f"📖 {d.get('title','')}")
        if not self.repo: self._init_db(d)
        self._status("构思完成 — 切换到大纲模式")

    def _out_done(self,raw):
        self.go_btn.setEnabled(True);self._status("")
        d=self._parse(raw)
        # 如果流式返回空或解析失败，用非流式重试
        if not d.get("volumes"):
            from src.models.llm_client import chat
            raw2=chat(self.cfg,P["outline"],
                f"已有设定:\n{json.dumps(self._idea,ensure_ascii=False)}\n规划{self.v_in.text() or '3'}卷×{self.c_in.text() or '4'}章")
            d=self._parse(raw2)
        if not d.get("volumes"):
            self._status("大纲生成失败，请重试");return
        if not self.repo: self._init_db(self._idea)
        self.repo.conn.execute("DELETE FROM outline_nodes WHERE novel_id=?",(self.repo.novel_id,))
        self.tree.clear();sort=0;total=0
        for vi,vol in enumerate(d.get("volumes",[]),1):
            vid=self._add_node(None,"volume",sort,f"第{vi}卷 {vol.get('title','')}","");sort+=1
            vi2=QTreeWidgetItem(self.tree,[f"📘 第{vi}卷 {vol.get('title','')}"]);vi2.setData(0,Qt.UserRole,vid)
            for ci,ch in enumerate(vol.get("chapters",[]),1):
                cid=self._add_node(vid,"chapter",sort,f"第{ci}章 {ch.get('title','')}",ch.get("summary",""));sort+=1
                ci2=QTreeWidgetItem(vi2,[f"📄 第{ci}章 {ch.get('title','')}"]);ci2.setData(0,Qt.UserRole,cid)
                # 每节带概要
                secs=ch.get("sections",[])
                if isinstance(secs,list):
                    for si,sec in enumerate(secs):
                        stitle=sec.get("title",f"第{si+1}节") if isinstance(sec,dict) else f"第{si+1}节"
                        ssum=sec.get("summary","") if isinstance(sec,dict) else ""
                        sid=self._add_node(cid,"section",sort,stitle,ssum);sort+=1;total+=1
                        QTreeWidgetItem(ci2,[f"📝 {stitle}"]).setData(0,Qt.UserRole,sid)
                else:
                    for si in range(secs if isinstance(secs,int) else 3):
                        sid=self._add_node(cid,"section",sort,f"第{si+1}节","");sort+=1;total+=1
                        QTreeWidgetItem(ci2,[f"📝 第{si+1}节"]).setData(0,Qt.UserRole,sid)
                ci2.setExpanded(True)
            vi2.setExpanded(True)
        self.repo.conn.commit()
        self._status("大纲完成 — 切换到写作模式")

    def _write_done(self,raw):
        self.go_btn.setEnabled(True);self._status("")
        if self.repo and self._nid:
            m=re.search(r'【本节摘要】[：:]\s*(.+?)(?:\n|$)',raw)
            self.repo.save_section(self._nid,raw,m.group(1) if m else "")
            self.repo.update_node_status(self._nid,"done")
            self._refresh_tree()
            p=self.repo.get_progress()
            self.prog_bar.setValue(int(p.get("progress_pct",0)))
            self.prog_lbl.setText(f"{p['done_sections']}/{p['total_sections']}节 · {p['total_words']:,}字")
            self.ctx_lbl.hide()
            self._status(f"完成 — {p['total_words']:,}字")

    def _init_db(self,d):
        self.repo=NovelRepository(f"novel_{int(time.time())}")
        n=time.strftime("%Y-%m-%dT%H:%M:%S")
        self.repo.conn.execute("INSERT INTO novels VALUES(?,?,?,?,?,?,?,?)",
            (self.repo.novel_id,d.get("title",""),d.get("genre",""),d.get("premise",""),"draft",0,n,n))
        for c in d.get("characters",[]):
            self.repo.conn.execute("INSERT INTO characters(novel_id,name,role,traits,arc,updated_at) VALUES(?,?,?,?,?,?)",
                (self.repo.novel_id,c["name"],c.get("role",""),c.get("traits",""),"",n))
        self.repo.conn.execute("INSERT INTO story_bible(project_id,category,key,value,source_scene,updated_at) VALUES(?,?,?,?,?,?)",
            (self.repo.novel_id,"world_rule","世界观",d.get("world_building",""),0,n))
        self.repo.conn.commit()

    def _add_node(self,pid,level,sort,title,summary):
        self.repo.conn.execute("INSERT INTO outline_nodes(novel_id,parent_id,level,sort_order,title,summary,status) VALUES(?,?,?,?,?,?,?)",
            (self.repo.novel_id,pid,level,sort,title,summary,"pending"))
        return self.repo.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _refresh_tree(self):
        if not self.repo:return
        data=self.repo.get_outline_tree()
        def up(item):
            nid=item.data(0,Qt.UserRole)
            if nid:
                n=next((x for x in data if x["id"]==nid),None)
                if n and n["status"]=="done":item.setForeground(0,QColor(C["green"]))
            for i in range(item.childCount()):up(item.child(i))
        for i in range(self.tree.topLevelItemCount()):up(self.tree.topLevelItem(i))

    def _parse(self,raw):
        try:
            s=raw
            if "```json" in s:s=s.split("```json")[1].split("```")[0]
            elif "```" in s:s=s.split("```")[1].split("```")[0]
            return json.loads(s.strip())
        except:return{}

    def _status(self,m):self.statusBar().showMessage(f"  {m}")


def main():
    app=QApplication(sys.argv)
    app.setStyle("Fusion")
    w=MainWin();w.show()
    sys.exit(app.exec_())

if __name__=="__main__":main()
