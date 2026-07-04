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
    "outline": "大纲策划。JSON:{volumes:[{title,chapters:[{title,summary,sections:3}]}]}。和已有角色世界观一致",
    "write":   "职业小说家。根据上下文写本节800-2000字。保持设定一致。末尾【本节摘要】一句话",
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

        # ── 中央区域 ──
        mid = QSplitter(Qt.Vertical)
        mid.setStyleSheet(f"QSplitter::handle{{background:{C['border']};height:1px;}}")

        # 大纲树
        tree_w=QWidget();tl=QVBoxLayout(tree_w);tl.setContentsMargins(0,0,0,0)
        hdr=QHBoxLayout();hdr.setContentsMargins(16,12,16,8)
        self.tree_title=QLabel("大纲");self.tree_title.setStyleSheet(f"color:{C['muted']};font-size:11px;font-weight:600;")
        hdr.addWidget(self.tree_title);hdr.addStretch()
        self.tree_cnt=QLabel("");self.tree_cnt.setStyleSheet(f"color:{C['muted']};font-size:11px;")
        hdr.addWidget(self.tree_cnt);tl.addLayout(hdr)
        self.tree=QTreeWidget()
        self.tree.setHeaderHidden(True);self.tree.setIndentation(16)
        self.tree.setStyleSheet(f"""
            QTreeWidget{{background:transparent;color:{C['text']};border:none;font-size:13px;}}
            QTreeWidget::item{{padding:4px 8px;border-radius:4px;}}
            QTreeWidget::item:hover{{background:{C['card']};}}
            QTreeWidget::item:selected{{background:#2a3a5c;color:{C['accent']};}}
        """)
        self.tree.itemClicked.connect(lambda i,_:self._tree_click(i))
        tl.addWidget(self.tree)
        mid.addWidget(tree_w)

        # 输出区
        out_w=QWidget();ol=QVBoxLayout(out_w);ol.setContentsMargins(16,8,16,12)
        oh=QHBoxLayout();oh.setContentsMargins(0,0,0,4)
        self.out_title=QLabel("输出");self.out_title.setStyleSheet(f"color:{C['muted']};font-size:11px;font-weight:600;")
        oh.addWidget(self.out_title);oh.addStretch()
        self.out_status=QLabel("");self.out_status.setStyleSheet(f"color:{C['yellow']};font-size:11px;")
        oh.addWidget(self.out_status);ol.addLayout(oh)
        self.content=QTextEdit();self.content.setReadOnly(True)
        self.content.setFont(QFont("Microsoft YaHei",13))
        self.content.setStyleSheet(f"""
            QTextEdit{{background:{C['bg']};color:{C['text']};border:1px solid {C['border']};
            border-radius:10px;padding:20px;line-height:1.9;selection-background:{C['accent']};}}
        """)
        self.content.setPlaceholderText("输出区")
        ol.addWidget(self.content)

        # 底部栏
        bar=QHBoxLayout()
        self.fb_in=QLineEdit();self.fb_in.setPlaceholderText("反馈意见 (Enter 发送)...");self.fb_in.returnPressed.connect(lambda:self._go("write"))
        self.fb_in.setStyleSheet(f"background:{C['card']};color:{C['text']};border:1px solid {C['border']};border-radius:8px;padding:10px 14px;font-size:13px;")
        bar.addWidget(self.fb_in)
        self.go_btn=QPushButton("执行");self.go_btn.clicked.connect(lambda:self._go(self._mode))
        self.go_btn.setStyleSheet(f"QPushButton{{background:{C['accent']};color:#000;border-radius:8px;padding:10px 24px;font-weight:600;}}QPushButton:hover{{opacity:0.9;}}QPushButton:disabled{{background:{C['card']};color:{C['muted']};}}")
        bar.addWidget(self.go_btn)
        ol.addLayout(bar)
        mid.addWidget(out_w)
        mid.setSizes([180,520])
        h.addWidget(mid)

        # ── 右边栏 ──
        right=QTabWidget()
        right.setStyleSheet(f"""
            QTabWidget::pane{{background:{C['bg']};border:none;}}
            QTabBar::tab{{background:{C['panel']};color:{C['muted']};padding:8px 16px;font-size:12px;border:none;}}
            QTabBar::tab:selected{{color:{C['accent']};border-bottom:2px solid {C['accent']};}}
        """)
        self.char_v=QTextBrowser();self.char_v.setStyleSheet(f"background:transparent;color:{C['text']};border:none;padding:12px;font-size:13px;")
        right.addTab(self.char_v,"角色")
        self.world_v=QTextBrowser();self.world_v.setStyleSheet(self.char_v.styleSheet())
        right.addTab(self.world_v,"世界观")
        h.addWidget(right)
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
        for r in npm.get(0,[]):build(None,r["id"])
        self.tree.expandAll()
        p=self.repo.get_progress()
        self.tree_cnt.setText(f"{p['done_sections']}/{p['total_sections']}节")
        self.prog_bar.setValue(int(p.get("progress_pct",0)))
        self.prog_lbl.setText(f"{p['done_sections']}/{p['total_sections']} 节 · {p['total_words']:,}字")
        self._status(f"已加载: {r['title']} — {p['total_words']:,}字")
        self._mode_switch(2)

    def _mode_switch(self, idx):
        modes=["idea","outline","write"];self._mode=modes[idx]
        self.stack.setCurrentIndex(idx)
        for i,b in enumerate(self.btns):b.setChecked(i==idx)

    def _tree_click(self, item):
        nid=item.data(0,Qt.UserRole)
        if nid and self.repo: self._nid=nid

    def _go(self, tag):
        if tag=="idea":
            idea=self.idea_in.toPlainText().strip()
            if not idea:return
            self.content.clear();self.out_status.setText("生成中...");self.go_btn.setEnabled(False)
            self._th=StreamThread(self.cfg,P["idea"],f"故事想法: {idea}")
            self._th.chunk.connect(self._chunk)
            self._th.done.connect(self._idea_done)
        elif tag=="outline":
            if not self._idea: self.content.setPlainText("请先生成构思");return
            self.content.clear();self.out_status.setText("生成中...");self.go_btn.setEnabled(False)
            v=self.v_in.text() or "3";c=self.c_in.text() or "4"
            u=f"已有设定:\n{json.dumps(self._idea,ensure_ascii=False)}\n规划{v}卷×{c}章"
            self._th=StreamThread(self.cfg,P["outline"],u)
            self._th.chunk.connect(self._chunk)
            self._th.done.connect(self._out_done)
        elif tag=="write":
            if not self.repo or not self._nid: self.content.setPlainText("请先生成大纲，点击左侧某一节");return
            self.content.clear();self.out_status.setText("写作中...");self.go_btn.setEnabled(False)
            ctx=self.repo.get_writing_context(self._nid)
            self.ctx_lbl.setText(f"上下文 ~{ctx['token_estimate']} tokens");self.ctx_lbl.show()
            n=self.repo.get_node(self._nid)
            fb=self.fb_in.text().strip();self.fb_in.clear()
            u=f"{ctx['context_text']}\n---\n大纲: {n['title']}\n{fb if fb else ''}\n请写本节:"
            self._th=StreamThread(self.cfg,P["write"],u)
            self._th.chunk.connect(self._chunk)
            self._th.done.connect(self._write_done)
        self._th.error.connect(lambda e:(self.content.setPlainText(f"错误: {e}"),self.go_btn.setEnabled(True)))
        self._th.start()

    def _chunk(self,t):
        c=self.content.textCursor();c.movePosition(QTextCursor.End);c.insertText(t)
        self.content.ensureCursorVisible()

    def _idea_done(self,raw):
        self.go_btn.setEnabled(True);self.out_status.setText("")
        d=self._parse(raw);self._idea=d
        chars="\n".join(f"{c['name']}({c.get('role','')}): {c.get('traits','')}" for c in d.get("characters",[]))
        self.content.setHtml(f"""
        <h2 style='color:{C["accent"]}'>{d.get('title','')}</h2>
        <p style='color:{C["muted"]}'>{d.get('genre','')} · {d.get('hook','')}</p>
        <blockquote style='color:{C["text"]};border-left:3px solid {C["accent"]};padding-left:12px;'>{d.get('premise','')}</blockquote>
        <h3 style='color:{C["muted"]}'>世界观</h3><p>{d.get('world_building','')}</p>
        <h3 style='color:{C["muted"]}'>角色</h3><pre style='color:{C["text"]}'>{chars}</pre>""")
        self.char_v.setText(chars);self.world_v.setText(d.get('world_building',''))
        self.proj_lbl.setText(f"📖 {d.get('title','')}")
        if not self.repo: self._init_db(d)
        self._status("构思完成 — 切换到大纲模式")

    def _out_done(self,raw):
        self.go_btn.setEnabled(True);self.out_status.setText("")
        d=self._parse(raw)
        if not self.repo: self._init_db(self._idea)
        self.repo.conn.execute("DELETE FROM outline_nodes WHERE novel_id=?",(self.repo.novel_id,))
        self.tree.clear();sort=0;total=0
        for vi,vol in enumerate(d.get("volumes",[]),1):
            vid=self._add_node(None,"volume",sort,f"第{vi}卷 {vol.get('title','')}","");sort+=1
            vi2=QTreeWidgetItem(self.tree,[f"📘 第{vi}卷 {vol.get('title','')}"]);vi2.setData(0,Qt.UserRole,vid)
            for ci,ch in enumerate(vol.get("chapters",[]),1):
                cid=self._add_node(vid,"chapter",sort,f"第{ci}章 {ch.get('title','')}",ch.get("summary",""));sort+=1
                ci2=QTreeWidgetItem(vi2,[f"📄 第{ci}章 {ch.get('title','')}"]);ci2.setData(0,Qt.UserRole,cid)
                for si in range(ch.get("sections",3)):
                    sid=self._add_node(cid,"section",sort,f"第{si+1}节","");sort+=1;total+=1
                    QTreeWidgetItem(ci2,[f"📝 第{si+1}节"]).setData(0,Qt.UserRole,sid)
                ci2.setExpanded(True)
            vi2.setExpanded(True)
        self.repo.conn.commit()
        self.tree_cnt.setText(f"{total}节")
        self._status("大纲完成 — 切换到写作模式")

    def _write_done(self,raw):
        self.go_btn.setEnabled(True);self.out_status.setText("")
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
