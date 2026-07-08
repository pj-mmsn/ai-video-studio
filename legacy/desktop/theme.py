"""
AI 小说家 — 主题配色与样式工厂
================================
所有颜色常量和可复用的 Qt 样式表集中管理。
"""

# ═══════════════════════════════════════════════ 配色 ═══════════════════════════════════════════════
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

# ═══════════════════════════════════════════════ 样式工厂 ═══════════════════════════════════════════════

def sidebar_btn_style():
    """侧边栏模式切换按钮"""
    return f"""
        QPushButton {{
            background: transparent; color: {C['muted']}; border: none; text-align: left;
            padding: 10px 14px; font-size: 13px; border-radius: 8px;
        }}
        QPushButton:hover {{ background: {C['card']}; color: {C['text']}; }}
        QPushButton:checked {{ background: #2a3a5c; color: {C['accent']}; font-weight: 600; }}
    """

def accent_btn_style():
    """主操作按钮（生成构思/大纲等）"""
    return f"""
        QPushButton {{
            background: {C['accent']}; color: #000; border-radius: 8px;
            padding: 10px; font-weight: 600;
        }}
        QPushButton:hover {{ opacity: 0.9; }}
        QPushButton:disabled {{ background: {C['card']}; color: {C['muted']}; }}
    """

def input_style():
    """文本输入框通用样式"""
    return f"""
        background: {C['card']}; color: {C['text']};
        border: 1px solid {C['border']}; border-radius: 8px;
        padding: 10px 14px; font-size: 13px;
    """

def text_edit_style():
    """QTextEdit 只读展示样式"""
    return f"""
        background: transparent; color: {C['text']};
        border: none; padding: 12px; font-size: 13px;
    """

def panel_style():
    """面板背景"""
    return f"background: {C['panel']};"

def body_style():
    """主窗口背景"""
    return f"background: {C['bg']};"

def global_scrollbar_style():
    """全局滚动条样式"""
    return f"""
        QScrollBar:vertical {{
            width: 10px; background: {C['bg']}; border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {C['border']}; border-radius: 5px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {C['accent']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            height: 10px; background: {C['bg']};
        }}
        QScrollBar::handle:horizontal {{
            background: {C['border']}; border-radius: 5px;
        }}
    """

def tab_style():
    """右侧标签页样式"""
    return f"""
        QTabWidget::pane {{ background: {C['bg']}; border: none; }}
        QTabBar::tab {{
            background: {C['panel']}; color: {C['muted']};
            padding: 8px 16px; font-size: 12px; border: none;
        }}
        QTabBar::tab:selected {{
            color: {C['accent']}; border-bottom: 2px solid {C['accent']};
        }}
    """

def tree_style():
    """大纲树样式"""
    return f"""
        QTreeWidget {{
            background: transparent; color: {C['text']}; border: none; font-size: 13px;
        }}
        QTreeWidget::item {{ padding: 4px 8px; border-radius: 4px; }}
        QTreeWidget::item:hover {{ background: {C['card']}; }}
        QTreeWidget::item:selected {{ background: #2a3a5c; color: {C['accent']}; }}
    """

def list_widget_style():
    """角色列表等 QListWidget 样式"""
    return f"""
        QListWidget {{
            background: {C['card']}; color: {C['text']};
            border: 1px solid {C['border']}; border-radius: 8px; font-size: 13px;
        }}
        QListWidget::item {{ padding: 10px 14px; border-bottom: 1px solid {C['border']}; }}
        QListWidget::item:hover {{ background: {C['bg']}; }}
        QListWidget::item:selected {{ background: #2a3a5c; color: {C['accent']}; }}
    """

def small_btn_style():
    """小按钮（角色面板的添加/编辑/删除）"""
    return f"""
        QPushButton {{
            background: {C['card']}; color: {C['text']}; border: 1px solid {C['border']};
            border-radius: 6px; padding: 6px 12px; font-size: 12px;
        }}
        QPushButton:hover {{ background: {C['border']}; }}
    """
