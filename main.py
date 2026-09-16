import sys
import os
import tempfile

# 必须在导入 PyQt5 之前设置
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'

from functools import partial

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar,
    QPlainTextEdit, QGroupBox, QFileDialog, QMessageBox, QAbstractItemView,
    QStatusBar, QScrollArea, QStackedWidget, QButtonGroup, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt5.QtGui import QPalette, QColor, QIcon

from config import Config
from ffmpeg_core import FFmpegWrapper, FileSorter, FFmpegWorker
from pdf_tools import (PdfWorker, DOC_EXTS, PDF_EXTS, font_path,
                       collect_files, word_to_pdf, set_pdf_permissions,
                       add_text_watermark, convert_to_image_pdf)
from video_watermark import (VideoWatermarkWorker, collect_videos,
                             probe_video, is_marked, build_command,
                             suggest_output)


def _fix_input_heights(widget):
    """QSS 的 min-height 不参与布局计算，会导致控件重叠，
    这里统一用固定高度，保证行距正常。"""
    for w in widget.findChildren((QLineEdit, QComboBox, QSpinBox,
                                  QDoubleSpinBox)):
        w.setFixedHeight(36)


APP_NAME = "媒体工具箱"
APP_TAGLINE = "视频 · PDF · 本地处理"

UI_ICONS = {}

THEMES = {
    "light": {
        "BG": "#eef3f1",
        "NAV_BG": "#ffffff",
        "CARD": "#ffffff",
        "INPUT_BG": "#f7faf9",
        "INPUT_FOCUS_BG": "#ffffff",
        "LOG_BG": "#f4f7f6",
        "BORDER": "#d7e0dd",
        "BORDER_HOVER": "#b7c7c2",
        "TEXT": "#1f2a28",
        "TEXT_MUTED": "#6b7c77",
        "TEXT_TITLE": "#2c3a37",
        "ACCENT": "#0d9f8a",
        "ACCENT_HOVER": "#0b8b79",
        "ACCENT_PRESSED": "#097365",
        "ACCENT_SOFT": "rgba(13, 159, 138, 0.12)",
        "ACCENT_SOFT2": "rgba(13, 159, 138, 0.18)",
        "ON_ACCENT": "#ffffff",
        "BTN_BG": "#ffffff",
        "BTN_TEXT": "#2c3a37",
        "BTN_HOVER": "#f3f8f6",
        "BTN_DISABLED_BG": "#eef3f1",
        "BTN_DISABLED_TEXT": "#9aa8a4",
        "DANGER": "#d45454",
        "DANGER_BORDER": "#f0b4b4",
        "DANGER_BG": "#fff6f6",
        "DANGER_HOVER": "#fdecec",
        "SUCCESS": "#1a9e6a",
        "WARNING": "#c9891a",
        "ERROR": "#d45454",
        "SCROLL": "#c5d2ce",
        "SCROLL_HOVER": "#9aada7",
        "HOVER_ITEM": "#f3f8f6",
        "SELECT_TEXT": "#0b8b79",
        "ICON": "#4a5d58",
        "CHECK": "#ffffff",
        "RADIUS": "8px",
        "RADIUS_SM": "6px",
    },
    "dark": {
        "BG": "#15191b",
        "NAV_BG": "#1a1f22",
        "CARD": "#1e2427",
        "INPUT_BG": "#15191b",
        "INPUT_FOCUS_BG": "#121618",
        "LOG_BG": "#121618",
        "BORDER": "#2c3438",
        "BORDER_HOVER": "#3d4a4e",
        "TEXT": "#e7eeec",
        "TEXT_MUTED": "#8b9a95",
        "TEXT_TITLE": "#d5e0dc",
        "ACCENT": "#2dd4bf",
        "ACCENT_HOVER": "#5eead4",
        "ACCENT_PRESSED": "#14b8a6",
        "ACCENT_SOFT": "rgba(45, 212, 191, 0.12)",
        "ACCENT_SOFT2": "rgba(45, 212, 191, 0.18)",
        "ON_ACCENT": "#042f2e",
        "BTN_BG": "#252c30",
        "BTN_TEXT": "#d5e0dc",
        "BTN_HOVER": "#2c3539",
        "BTN_DISABLED_BG": "#1a1f22",
        "BTN_DISABLED_TEXT": "#5c6b67",
        "DANGER": "#f0a0a0",
        "DANGER_BORDER": "#7f1d1d",
        "DANGER_BG": "#2a1616",
        "DANGER_HOVER": "#3a1c1c",
        "SUCCESS": "#34d399",
        "WARNING": "#fbbf24",
        "ERROR": "#f87171",
        "SCROLL": "#3d4a4e",
        "SCROLL_HOVER": "#5c6b67",
        "HOVER_ITEM": "#252c30",
        "SELECT_TEXT": "#5eead4",
        "ICON": "#c5d4cf",
        "CHECK": "#042f2e",
        "RADIUS": "8px",
        "RADIUS_SM": "6px",
    },
}


def _hex_rgba(value):
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16),
            int(value[4:6], 16), 255)


def _gen_ui_icons(theme=None):
    """按当前主题生成箭头 / 对勾 / 导航图标。"""
    from PIL import Image, ImageDraw

    theme = theme or THEMES["light"]
    d = os.path.join(tempfile.gettempdir(), "MediaKit_ui")
    os.makedirs(d, exist_ok=True)
    gray = _hex_rgba(theme["ICON"])
    accent = _hex_rgba(theme["ACCENT"])
    check = _hex_rgba(theme["CHECK"])
    icon = _hex_rgba(theme["ICON"])

    def _save(name, size, draw_fn):
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw_fn(ImageDraw.Draw(img))
        path = os.path.join(d, name)
        img.save(path)
        return path.replace("\\", "/")

    def _stroke_icon(draw_fn):
        def _inner(dr):
            draw_fn(dr, icon)
        return _inner

    icons = {
        "__ICON_DOWN__": _save(
            "arrow_down.png", (12, 8),
            lambda dr: dr.polygon([(0, 0), (12, 0), (6, 8)], fill=gray)),
        "__ICON_DOWN_FOCUS__": _save(
            "arrow_down_focus.png", (12, 8),
            lambda dr: dr.polygon([(0, 0), (12, 0), (6, 8)], fill=accent)),
        "__ICON_UP__": _save(
            "arrow_up.png", (12, 8),
            lambda dr: dr.polygon([(0, 8), (12, 8), (6, 0)], fill=gray)),
        "__ICON_CHECK__": _save(
            "check.png", (14, 12),
            lambda dr: dr.line([(2, 6), (5, 9), (12, 2)],
                               fill=check, width=2)),
        "__NAV_MERGE__": _save(
            "nav_merge.png", (20, 20),
            _stroke_icon(lambda dr, c: (
                dr.rectangle([1, 5, 12, 16], outline=c, width=2),
                dr.rectangle([8, 3, 19, 14], outline=c, width=2),
            ))),
        "__NAV_COMPRESS__": _save(
            "nav_compress.png", (20, 20),
            _stroke_icon(lambda dr, c: (
                dr.line([(4, 5), (10, 11), (16, 5)], fill=c, width=2),
                dr.line([(4, 10), (10, 16), (16, 10)], fill=c, width=2),
            ))),
        "__NAV_WATERMARK__": _save(
            "nav_watermark.png", (20, 20),
            _stroke_icon(lambda dr, c: (
                dr.polygon([(10, 2), (17, 11), (10, 18), (3, 11)], outline=c),
                dr.ellipse([7, 8, 13, 14], outline=c, width=2),
            ))),
        "__NAV_PDF__": _save(
            "nav_pdf.png", (20, 20),
            _stroke_icon(lambda dr, c: (
                dr.polygon([(4, 2), (12, 2), (16, 6), (16, 18), (4, 18)],
                           outline=c),
                dr.line([(12, 2), (12, 6), (16, 6)], fill=c, width=2),
            ))),
        "__NAV_SETTINGS__": _save(
            "nav_settings.png", (20, 20),
            _stroke_icon(lambda dr, c: (
                dr.ellipse([3, 3, 17, 17], outline=c, width=2),
                dr.ellipse([7, 7, 13, 13], outline=c, width=2),
            ))),
        "__NAV_DOT__": _save(
            "nav_dot.png", (8, 8),
            lambda dr: dr.ellipse([0, 0, 7, 7], fill=gray)),
    }
    global UI_ICONS
    UI_ICONS = icons
    return icons


# ==================== 明暗主题（小圆角卡片） ====================
STYLE_TEMPLATE = """
/* === 基础 === */
QMainWindow, QDialog {
    background-color: __BG__;
}
QWidget {
    color: __TEXT__;
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 13px;
    background-color: transparent;
}

/* === 侧栏 === */
QWidget#navRail {
    background-color: __NAV_BG__;
    border-right: 1px solid __BORDER__;
}
QLabel#brandTitle {
    color: __TEXT__;
    font-size: 16px;
    font-weight: 700;
    padding: 0px;
}
QLabel#brandSub {
    color: __TEXT_MUTED__;
    font-size: 11px;
    padding: 0px 0px 4px 0px;
}
QLabel#navStatus {
    color: __TEXT_MUTED__;
    font-size: 11px;
    padding: 8px 4px 0px 4px;
}
QPushButton#navItem {
    background-color: transparent;
    color: __TEXT_MUTED__;
    border: none;
    border-radius: __RADIUS_SM__;
    text-align: left;
    padding: 9px 12px;
    min-height: 20px;
    font-weight: 500;
    font-size: 13px;
}
QPushButton#navItem:hover {
    background-color: __HOVER_ITEM__;
    color: __TEXT__;
}
QPushButton#navItem:checked {
    background-color: __ACCENT_SOFT__;
    color: __ACCENT__;
    font-weight: 600;
}
QPushButton#navItem:pressed {
    background-color: __ACCENT_SOFT__;
}
QPushButton#themeToggle {
    background-color: __BTN_BG__;
    color: __BTN_TEXT__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS_SM__;
    padding: 6px 10px;
    min-height: 18px;
    font-weight: 500;
}
QPushButton#themeToggle:hover {
    border-color: __ACCENT__;
    color: __ACCENT__;
}

/* === 功能平铺卡片（互斥选择） === */
QPushButton#modeCard {
    background-color: __BTN_BG__;
    color: __TEXT_MUTED__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS__;
    padding: 12px 10px;
    min-height: 24px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton#modeCard:hover {
    border-color: __ACCENT__;
    color: __TEXT__;
    background-color: __HOVER_ITEM__;
}
QPushButton#modeCard:checked {
    background-color: __ACCENT_SOFT2__;
    border: 1px solid __ACCENT__;
    color: __ACCENT__;
    font-weight: 700;
}

/* === 按钮 === */
QPushButton {
    background-color: __BTN_BG__;
    color: __BTN_TEXT__;
    border: 1px solid __BORDER__;
    padding: 7px 14px;
    border-radius: __RADIUS_SM__;
    min-height: 22px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: __BTN_HOVER__;
    border-color: __ACCENT__;
    color: __TEXT__;
}
QPushButton:pressed {
    background-color: __HOVER_ITEM__;
    border-color: __ACCENT__;
}
QPushButton:disabled {
    background-color: __BTN_DISABLED_BG__;
    color: __BTN_DISABLED_TEXT__;
    border-color: __BORDER__;
}
QPushButton#primary {
    background-color: __ACCENT__;
    color: __ON_ACCENT__;
    border: none;
    min-height: 24px;
    font-weight: 700;
    border-radius: __RADIUS__;
}
QPushButton#primary:hover {
    background-color: __ACCENT_HOVER__;
}
QPushButton#primary:pressed {
    background-color: __ACCENT_PRESSED__;
}
QPushButton#primary:disabled {
    background-color: __ACCENT_SOFT2__;
    color: __TEXT_MUTED__;
}
QPushButton#cancel {
    background-color: __DANGER_BG__;
    color: __DANGER__;
    border: 1px solid __DANGER_BORDER__;
    font-weight: 500;
}
QPushButton#cancel:hover {
    background-color: __DANGER_HOVER__;
}

/* === 列表 === */
QListWidget {
    background-color: __INPUT_BG__;
    border: 1px dashed __BORDER_HOVER__;
    border-radius: __RADIUS__;
    padding: 8px;
    outline: none;
}
QListWidget[hasItems="true"] {
    border: 1px solid __BORDER__;
    border-style: solid;
}
QListWidget::item {
    padding: 9px 12px;
    border-radius: __RADIUS_SM__;
    color: __TEXT__;
    margin: 2px 0px;
}
QListWidget::item:selected {
    background-color: __ACCENT_SOFT2__;
    color: __SELECT_TEXT__;
}
QListWidget::item:hover:!selected {
    background-color: __HOVER_ITEM__;
}
QLabel#emptyHint {
    color: __TEXT_MUTED__;
    font-size: 13px;
    background: transparent;
}

/* === 输入框 === */
QLineEdit, QAbstractSpinBox, QComboBox {
    background-color: __INPUT_BG__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS_SM__;
    padding: 0px 12px;
    color: __TEXT__;
    selection-background-color: __ACCENT_SOFT2__;
    selection-color: __SELECT_TEXT__;
}
QLineEdit:hover, QAbstractSpinBox:hover, QComboBox:hover {
    border-color: __BORDER_HOVER__;
}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {
    border: 1px solid __ACCENT__;
    background-color: __INPUT_FOCUS_BG__;
}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {
    color: __BTN_DISABLED_TEXT__;
    border-color: __BORDER__;
    background-color: __BTN_DISABLED_BG__;
}

/* === 下拉框 === */
QComboBox::drop-down {
    border: none;
    width: 32px;
}
QComboBox::drop-down:hover {
    background-color: __ACCENT_SOFT__;
    border-top-right-radius: __RADIUS_SM__;
    border-bottom-right-radius: __RADIUS_SM__;
}
QComboBox::down-arrow {
    image: url("__ICON_DOWN__");
    width: 12px;
    height: 8px;
}
QComboBox QAbstractItemView {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS__;
    color: __TEXT__;
    selection-background-color: __ACCENT_SOFT2__;
    selection-color: __SELECT_TEXT__;
    outline: none;
    padding: 6px;
}
QComboBox QAbstractItemView::item {
    padding: 8px 12px;
    border-radius: __RADIUS_SM__;
    min-height: 20px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: __HOVER_ITEM__;
}
QComboBox QAbstractItemView::item:selected {
    background-color: __ACCENT_SOFT2__;
    color: __SELECT_TEXT__;
}

QAbstractSpinBox {
    padding-right: 30px;
}

/* === 数字框箭头 === */
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    background-color: transparent;
    border: none;
    width: 24px;
    height: 18px;
    border-radius: 4px;
}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {
    background-color: __ACCENT_SOFT__;
}
QAbstractSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
}
QAbstractSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
}
QAbstractSpinBox::up-arrow {
    image: url("__ICON_UP__");
    width: 12px;
    height: 8px;
}
QAbstractSpinBox::down-arrow {
    image: url("__ICON_DOWN__");
    width: 12px;
    height: 8px;
}

/* === 进度条 === */
QProgressBar {
    background-color: __INPUT_BG__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS_SM__;
    text-align: center;
    color: __TEXT__;
    min-height: 18px;
    font-weight: 600;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: __ACCENT__;
    border-radius: __RADIUS_SM__;
}

/* === 日志框 === */
QPlainTextEdit {
    background-color: __LOG_BG__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS__;
    color: __TEXT_MUTED__;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 8px;
}

/* === 卡片 === */
QGroupBox {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS__;
    margin-top: 10px;
    padding-top: 34px;
    padding-bottom: 14px;
    padding-left: 14px;
    padding-right: 14px;
    color: __TEXT__;
    font-weight: 600;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    top: 10px;
    left: 12px;
    background-color: transparent;
    color: __TEXT_TITLE__;
    font-size: 13px;
    font-weight: 700;
}

/* === 滚动区域 === */
QScrollArea {
    background-color: __BG__;
    border: none;
}
QScrollArea > QWidget {
    background-color: __BG__;
}
QWidget#pageContent {
    background-color: __BG__;
}

/* === 复选框 === */
QCheckBox {
    color: __TEXT__;
    spacing: 10px;
    padding: 4px 0px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid __BORDER_HOVER__;
    background-color: __INPUT_BG__;
}
QCheckBox::indicator:checked {
    background-color: __ACCENT__;
    border-color: __ACCENT__;
    image: url("__ICON_CHECK__");
}
QCheckBox::indicator:hover {
    border-color: __ACCENT__;
}
QCheckBox::indicator:checked:hover {
    background-color: __ACCENT_HOVER__;
    border-color: __ACCENT_HOVER__;
}

/* === 标签状态色 === */
QLabel#info { color: __TEXT_MUTED__; }
QLabel#success { color: __SUCCESS__; font-weight: 600; }
QLabel#warning { color: __WARNING__; font-weight: 600; }
QLabel#error { color: __ERROR__; font-weight: 600; }

/* === 状态栏 === */
QStatusBar {
    background-color: __NAV_BG__;
    color: __TEXT_MUTED__;
    border-top: 1px solid __BORDER__;
    padding: 4px 14px;
    font-size: 12px;
}

/* === 滚动条 === */
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    border: none;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background-color: __SCROLL__;
    border-radius: 5px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background-color: __SCROLL_HOVER__;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar:horizontal {
    background-color: transparent;
    height: 10px;
    border: none;
    margin: 2px 4px;
}
QScrollBar::handle:horizontal {
    background-color: __SCROLL__;
    border-radius: 5px;
    min-width: 40px;
}
QScrollBar::handle:horizontal:hover {
    background-color: __SCROLL_HOVER__;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* === 工具提示 === */
QToolTip {
    background-color: __CARD__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS_SM__;
    padding: 6px 10px;
    font-size: 12px;
}

/* === 菜单 / 对话框 === */
QMenu {
    background-color: __CARD__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: __RADIUS__;
    padding: 6px;
}
QMenu::item {
    padding: 8px 24px;
    border-radius: __RADIUS_SM__;
}
QMenu::item:selected {
    background-color: __ACCENT_SOFT2__;
    color: __SELECT_TEXT__;
}
QMessageBox {
    background-color: __CARD__;
}
QMessageBox QLabel {
    color: __TEXT__;
}

QStackedWidget {
    background: transparent;
}
QStackedWidget > QWidget > QWidget {
    background: transparent;
}
"""


def _render_style(theme, icons):
    style = STYLE_TEMPLATE
    for key, value in theme.items():
        style = style.replace("__" + key + "__", str(value))
    for key, path in icons.items():
        style = style.replace(key, path)
    return style


def _apply_palette(app, theme):
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(theme["BG"]))
    pal.setColor(QPalette.WindowText, QColor(theme["TEXT"]))
    pal.setColor(QPalette.Base, QColor(theme["INPUT_BG"]))
    pal.setColor(QPalette.AlternateBase, QColor(theme["CARD"]))
    pal.setColor(QPalette.ToolTipBase, QColor(theme["CARD"]))
    pal.setColor(QPalette.ToolTipText, QColor(theme["TEXT"]))
    pal.setColor(QPalette.Text, QColor(theme["TEXT"]))
    pal.setColor(QPalette.Button, QColor(theme["BTN_BG"]))
    pal.setColor(QPalette.ButtonText, QColor(theme["BTN_TEXT"]))
    pal.setColor(QPalette.Highlight, QColor(theme["ACCENT"]))
    pal.setColor(QPalette.HighlightedText, QColor(theme["ON_ACCENT"]))
    pal.setColor(QPalette.PlaceholderText, QColor(theme["TEXT_MUTED"]))
    app.setPalette(pal)


def apply_app_theme(app, name):
    """应用浅色或深色主题，并刷新图标。"""
    if name not in THEMES:
        name = "light"
    theme = THEMES[name]
    icons = _gen_ui_icons(theme)
    _apply_palette(app, theme)
    app.setStyleSheet(_render_style(theme, icons))
    return name, icons


# ==================== 自定义控件 ====================
class FileListWidget(QListWidget):
    """支持外部文件拖放和内部拖拽排序的列表控件"""
    files_dropped = pyqtSignal(list)
    reordered = pyqtSignal()

    def __init__(self, parent=None, empty_text="拖拽文件到此处\n或点击「添加文件」"):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._empty = QLabel(empty_text, self)
        self._empty.setObjectName("emptyHint")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.model().rowsInserted.connect(self._sync_empty)
        self.model().rowsRemoved.connect(self._sync_empty)
        self.model().modelReset.connect(self._sync_empty)
        self._sync_empty()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._empty.setGeometry(self.viewport().rect())

    def showEvent(self, event):
        super().showEvent(event)
        self._empty.setGeometry(self.viewport().rect())
        self._sync_empty()

    def _sync_empty(self, *args):
        has = self.count() > 0
        self._empty.setVisible(not has)
        self.setProperty("hasItems", "true" if has else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    fp = url.toLocalFile()
                    if os.path.isfile(fp):
                        files.append(fp)
            if files:
                self.files_dropped.emit(files)
                event.acceptProposedAction()
        else:
            super().dropEvent(event)
            self.reordered.emit()


class DropLineEdit(QLineEdit):
    """支持拖放文件的单行输入框"""
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    fp = url.toLocalFile()
                    if os.path.isfile(fp):
                        self.file_dropped.emit(fp)
                        event.acceptProposedAction()
                        break
        else:
            super().dropEvent(event)


# ==================== 合并页签 ====================
class MergeTab(QWidget):
    def __init__(self, config, status_bar, parent=None):
        super().__init__(parent)
        self.config = config
        self.status_bar = status_bar
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("pageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 文件卡片
        file_group = QGroupBox("文件列表")
        f_layout = QVBoxLayout(file_group)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(10)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.btn_add = QPushButton("＋ 添加文件")
        self.btn_remove = QPushButton("－ 删除选中")
        self.btn_clear = QPushButton("× 清空")
        self.btn_up = QPushButton("↑ 上移")
        self.btn_down = QPushButton("↓ 下移")
        self.btn_sort = QPushButton("⇅ 自动排序")
        for btn in (self.btn_add, self.btn_remove, self.btn_clear):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        for btn in (self.btn_up, self.btn_down, self.btn_sort):
            toolbar.addWidget(btn)
        f_layout.addLayout(toolbar)

        # 提示
        hint = QLabel("拖入文件即可添加，列表内拖拽可调整顺序")
        hint.setObjectName("info")
        f_layout.addWidget(hint)

        # 文件列表
        self.file_list = FileListWidget(
            empty_text="拖拽视频到此处\n或点击「添加文件」")
        self.file_list.setMinimumHeight(240)
        f_layout.addWidget(self.file_list, 1)
        layout.addWidget(file_group)

        # 输出卡片
        out_group = QGroupBox("输出")
        o_layout = QVBoxLayout(out_group)
        o_layout.setContentsMargins(0, 0, 0, 0)
        o_layout.setSpacing(10)
        out_layout = QHBoxLayout()
        out_layout.setSpacing(10)
        out_layout.addWidget(QLabel("输出文件:"))
        self.txt_output = QLineEdit()
        self.btn_browse_out = QPushButton("浏览...")
        out_layout.addWidget(self.txt_output, 1)
        out_layout.addWidget(self.btn_browse_out)
        o_layout.addLayout(out_layout)
        opt_layout = QHBoxLayout()
        self.chk_reencode = QCheckBox("编码不一致时重编码合并")
        self.chk_reencode.setChecked(True)
        opt_layout.addWidget(self.chk_reencode)
        opt_layout.addStretch()
        o_layout.addLayout(opt_layout)
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("info")
        o_layout.addWidget(self.lbl_status)
        layout.addWidget(out_group)

        # 开始按钮 + 取消按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_merge = QPushButton("开始合并")
        self.btn_merge.setObjectName("primary")
        self.btn_merge.setMinimumHeight(44)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("cancel")
        self.btn_cancel.setMinimumHeight(44)
        self.btn_cancel.setVisible(False)
        btn_row.addWidget(self.btn_merge, 1)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        # 进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 日志
        self.log = QPlainTextEdit()
        self.log.setMaximumHeight(140)
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("处理日志会显示在这里")
        layout.addWidget(self.log)

        # 信号
        self.btn_add.clicked.connect(self._add_files)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_up.clicked.connect(lambda: self._move_item(-1))
        self.btn_down.clicked.connect(lambda: self._move_item(1))
        self.btn_sort.clicked.connect(self._auto_sort)
        self.btn_browse_out.clicked.connect(self._browse_output)
        self.btn_merge.clicked.connect(self._start_merge)
        self.btn_cancel.clicked.connect(self._cancel_merge)
        self.file_list.files_dropped.connect(self._add_file_paths)
        self.file_list.reordered.connect(self._update_indices)

        # 内容装入滚动区域后，再统一输入控件高度（content 需已是 self 的子控件）
        scroll.setWidget(content)
        outer.addWidget(scroll)
        _fix_input_heights(self)

    def _get_ff(self):
        return FFmpegWrapper(
            self.config.get("ffmpeg_path", ""),
            self.config.get("ffprobe_path", "")
        )

    def _add_files(self):
        last_dir = self.config.get("last_output_dir", "")
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", last_dir,
            "视频文件 (*.flv *.mp4 *.mkv *.avi *.ts *.mov *.wmv);;所有文件 (*)"
        )
        if files:
            self._add_file_paths(files)
            self.config.set("last_output_dir", os.path.dirname(files[0]))

    def _add_file_paths(self, files):
        for f in files:
            if f not in [self.file_list.item(i).data(Qt.UserRole)
                         for i in range(self.file_list.count())]:
                size = os.path.getsize(f)
                size_str = FFmpegWrapper.format_size(size)
                item = QListWidgetItem(f"{os.path.basename(f)}  ({size_str})")
                item.setData(Qt.UserRole, f)
                self.file_list.addItem(item)
        self._auto_sort()
        self._check_compatibility()
        if not self.txt_output.text():
            self._suggest_output()

    def _suggest_output(self):
        if self.file_list.count() == 0:
            return
        first = self.file_list.item(0).data(Qt.UserRole)
        base = os.path.splitext(os.path.basename(first))[0]
        # 去除时间戳前缀
        import re
        base = re.sub(r'^\d{8}[-_]?\d{6}[-_]', '', base)
        base = re.sub(r'^\d{4}[-_]\d{2}[-_]\d{2}([-_]\d{2}[-_]\d{2}[-_]\d{2})?', '', base)
        if not base:
            base = "output"
        out_dir = self.config.get("last_output_dir", "") or os.path.dirname(first)
        self.txt_output.setText(os.path.join(out_dir, f"{base}_合并.mp4"))

    def _update_indices(self):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            text = item.text()
            if ". " in text:
                text = text.split(". ", 1)[1]
            item.setText(f"{i+1}. {text}")

    def _remove_selected(self):
        for item in reversed(self.file_list.selectedItems()):
            self.file_list.takeItem(self.file_list.row(item))
        self._update_indices()
        self._check_compatibility()

    def _clear_all(self):
        self.file_list.clear()
        self.lbl_status.setText("")
        self.txt_output.clear()

    def _move_item(self, direction):
        row = self.file_list.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if 0 <= new_row < self.file_list.count():
            item = self.file_list.takeItem(row)
            self.file_list.insertItem(new_row, item)
            self.file_list.setCurrentRow(new_row)
            self._update_indices()

    def _auto_sort(self):
        paths = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        if not paths:
            return
        sorted_paths = FileSorter.sort_files(paths)
        self.file_list.clear()
        for f in sorted_paths:
            size = os.path.getsize(f)
            size_str = FFmpegWrapper.format_size(size)
            item = QListWidgetItem(f"{os.path.basename(f)}  ({size_str})")
            item.setData(Qt.UserRole, f)
            self.file_list.addItem(item)
        self._update_indices()

    def _check_compatibility(self):
        paths = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        if len(paths) < 2:
            self.lbl_status.setText("")
            return
        ff = self._get_ff()
        if not ff.ffprobe or not os.path.exists(ff.ffprobe):
            self.lbl_status.setText("⚠ 未找到 FFprobe，无法检查编码")
            self.lbl_status.setObjectName("warning")
        else:
            ok, msg, _ = ff.check_compatibility(paths)
            if ok:
                self.lbl_status.setText(f"✓ {msg}")
                self.lbl_status.setObjectName("success")
            else:
                self.lbl_status.setText(f"⚠ {msg}")
                self.lbl_status.setObjectName("warning")
        self.style().unpolish(self.lbl_status)
        self.style().polish(self.lbl_status)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出文件", "", "MP4 文件 (*.mp4);;MKV 文件 (*.mkv);;所有文件 (*)"
        )
        if path:
            self.txt_output.setText(path)

    def _start_merge(self):
        paths = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        if len(paths) < 2:
            QMessageBox.warning(self, "提示", "请至少添加 2 个文件")
            return
        output = self.txt_output.text().strip()
        if not output:
            QMessageBox.warning(self, "提示", "请选择输出文件")
            return
        ff_path = self.config.get("ffmpeg_path", "")
        if not ff_path or not os.path.exists(ff_path):
            QMessageBox.warning(self, "提示", "未找到可用的 FFmpeg")
            return

        ff = self._get_ff()
        ok, msg, infos = ff.check_compatibility(paths)
        re_encode = self.chk_reencode.isChecked() and not ok
        total_duration = sum(info["duration"] for _, info in infos) if infos else 0

        cmd, temp_file = ff.build_merge_command(
            paths, output, re_encode=re_encode,
            codec=self.config.get("default_codec", "hevc_nvenc"),
            use_nvenc=self.config.get("use_nvenc", True),
            audio_bitrate=self.config.get("default_audio_bitrate", 128)
        )
        self._run_worker(cmd, total_duration, temp_file)

    def _run_worker(self, cmd, duration, temp_file=None):
        self.worker = FFmpegWorker(cmd, duration, temp_file)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.btn_merge.setEnabled(False)
        self.btn_merge.setText("处理中...")
        self.btn_cancel.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log.clear()
        self.worker.start()

    def _cancel_merge(self):
        if self.worker and self.worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("取消中...")
            self.worker.cancel()

    def _on_progress(self, pct):
        self.progress.setValue(pct)

    def _on_log(self, msg):
        self.log.appendPlainText(msg)

    def _on_finished(self, success, msg):
        self.btn_merge.setEnabled(True)
        self.btn_merge.setText("开始合并")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("取消")
        if success:
            self.progress.setValue(100)
            QMessageBox.information(self, "成功", f"合并完成\n{msg}")
        else:
            QMessageBox.warning(self, "失败", f"合并失败\n{msg}")


# ==================== 压缩页签 ====================
class CompressTab(QWidget):
    def __init__(self, config, status_bar, parent=None):
        super().__init__(parent)
        self.config = config
        self.status_bar = status_bar
        self.worker = None
        self.file_info = None
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("pageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 文件选择
        file_group = QGroupBox("文件")
        file_layout = QGridLayout(file_group)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setHorizontalSpacing(12)
        file_layout.setVerticalSpacing(12)
        file_layout.addWidget(QLabel("源文件:"), 0, 0)
        self.txt_input = DropLineEdit()
        self.txt_input.setPlaceholderText("可拖拽文件到此处")
        self.btn_browse_in = QPushButton("浏览...")
        file_layout.addWidget(self.txt_input, 0, 1)
        file_layout.addWidget(self.btn_browse_in, 0, 2)
        file_layout.addWidget(QLabel("输出文件:"), 1, 0)
        self.txt_output = QLineEdit()
        self.txt_output.setPlaceholderText("留空则默认与源文件同目录")
        self.btn_browse_out = QPushButton("浏览...")
        file_layout.addWidget(self.txt_output, 1, 1)
        file_layout.addWidget(self.btn_browse_out, 1, 2)
        file_layout.setColumnStretch(1, 1)
        layout.addWidget(file_group)

        # 压缩设置
        settings_group = QGroupBox("压缩设置")
        s_layout = QGridLayout(settings_group)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setHorizontalSpacing(12)
        s_layout.setVerticalSpacing(12)
        s_layout.addWidget(QLabel("输出格式:"), 0, 0)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["同源格式", "MP4", "MKV", "AVI", "TS"])
        s_layout.addWidget(self.cmb_format, 0, 1)
        s_layout.addWidget(QLabel("视频编码:"), 1, 0)
        self.cmb_codec = QComboBox()
        self.cmb_codec.addItems(["HEVC (H.265) NVENC", "H.264 NVENC",
                                  "HEVC (H.265) 软解", "H.264 软解"])
        s_layout.addWidget(self.cmb_codec, 1, 1)
        s_layout.addWidget(QLabel("目标大小:"), 2, 0)
        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self.cmb_size = QComboBox()
        self.cmb_size.addItems(["500 MB", "1 GB", "2 GB", "自定义"])
        self.cmb_size.setCurrentText("1 GB")
        self.lbl_custom = QLabel("自定义:")
        self.txt_custom = QSpinBox()
        self.txt_custom.setRange(10, 99999)
        self.txt_custom.setValue(1024)
        self.txt_custom.setSuffix(" MB")
        self.lbl_custom.setVisible(False)
        self.txt_custom.setVisible(False)
        size_row.addWidget(self.cmb_size)
        size_row.addWidget(self.lbl_custom)
        size_row.addWidget(self.txt_custom)
        size_row.addStretch()
        s_layout.addLayout(size_row, 2, 1)
        s_layout.addWidget(QLabel("音频码率:"), 3, 0)
        audio_row = QHBoxLayout()
        self.spn_audio = QSpinBox()
        self.spn_audio.setRange(32, 512)
        self.spn_audio.setValue(128)
        self.spn_audio.setSuffix(" kbps")
        audio_row.addWidget(self.spn_audio)
        audio_row.addStretch()
        s_layout.addLayout(audio_row, 3, 1)
        s_layout.setColumnStretch(1, 1)
        layout.addWidget(settings_group)

        # 文件信息
        info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_info = QLabel("请选择源文件")
        self.lbl_info.setObjectName("info")
        info_layout.addWidget(self.lbl_info)
        layout.addWidget(info_group)

        # 开始按钮 + 取消按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_compress = QPushButton("开始压缩")
        self.btn_compress.setObjectName("primary")
        self.btn_compress.setMinimumHeight(44)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("cancel")
        self.btn_cancel.setMinimumHeight(44)
        self.btn_cancel.setVisible(False)
        btn_row.addWidget(self.btn_compress, 1)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        # 进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 日志
        self.log = QPlainTextEdit()
        self.log.setMaximumHeight(140)
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("处理日志会显示在这里")
        layout.addWidget(self.log)

        # 信号
        self.btn_browse_in.clicked.connect(self._browse_input)
        self.btn_browse_out.clicked.connect(self._browse_output)
        self.btn_compress.clicked.connect(self._start_compress)
        self.btn_cancel.clicked.connect(self._cancel_compress)
        self.cmb_size.currentTextChanged.connect(self._on_size_changed)
        self.txt_input.textChanged.connect(self._on_input_changed)
        self.txt_input.file_dropped.connect(self._on_file_dropped)
        self.cmb_format.currentTextChanged.connect(self._update_output_ext)
        _fix_input_heights(content)

        # 内容装入滚动区域，窗口不够高时可滚动，不再挤压重叠
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _on_size_changed(self, text):
        is_custom = text == "自定义"
        self.lbl_custom.setVisible(is_custom)
        self.txt_custom.setVisible(is_custom)

    def _on_file_dropped(self, path):
        self.txt_input.setText(path)
        self.config.set("last_output_dir", os.path.dirname(path))

    def _browse_input(self):
        last_dir = self.config.get("last_output_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择源文件", last_dir,
            "视频文件 (*.mp4 *.mkv *.flv *.avi *.ts *.mov *.wmv);;所有文件 (*)"
        )
        if path:
            self.txt_input.setText(path)
            self.config.set("last_output_dir", os.path.dirname(path))

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出文件", "", "MP4 文件 (*.mp4);;MKV 文件 (*.mkv);;所有文件 (*)"
        )
        if path:
            self.txt_output.setText(path)

    def _on_input_changed(self):
        path = self.txt_input.text().strip()
        if path and os.path.exists(path):
            self._probe_file(path)
            self._update_output_path()

    def _probe_file(self, path):
        ff = FFmpegWrapper(
            self.config.get("ffmpeg_path", ""),
            self.config.get("ffprobe_path", "")
        )
        info = ff.parse_probe(ff.probe(path))
        if info:
            self.file_info = info
            size = os.path.getsize(path)
            dur = FFmpegWrapper.format_duration(info["duration"])
            res = f"{info['video']['width']}x{info['video']['height']}"
            codec = info["video"]["codec"]
            self.lbl_info.setText(
                f"分辨率: {res}  |  时长: {dur}  |  "
                f"大小: {FFmpegWrapper.format_size(size)}  |  编码: {codec}"
            )
            self.lbl_info.setObjectName("info")
        else:
            self.file_info = None
            self.lbl_info.setText("无法读取文件信息")
            self.lbl_info.setObjectName("warning")
        self.style().unpolish(self.lbl_info)
        self.style().polish(self.lbl_info)

    def _update_output_path(self):
        input_path = self.txt_input.text().strip()
        if not input_path:
            return
        base = os.path.splitext(input_path)[0]
        ext = self._get_output_ext()
        self.txt_output.setText(f"{base}_compressed{ext}")

    def _update_output_ext(self):
        if self.txt_output.text().strip():
            path = self.txt_output.text().strip()
            base = os.path.splitext(path)[0]
            self.txt_output.setText(f"{base}{self._get_output_ext()}")

    def _get_output_ext(self):
        fmt = self.cmb_format.currentText()
        if fmt == "同源格式":
            input_path = self.txt_input.text().strip()
            if input_path:
                return os.path.splitext(input_path)[1]
            return ".mp4"
        ext_map = {"MP4": ".mp4", "MKV": ".mkv", "AVI": ".avi", "TS": ".ts"}
        return ext_map.get(fmt, ".mp4")

    def _get_target_size_mb(self):
        text = self.cmb_size.currentText()
        if text == "自定义":
            return self.txt_custom.value()
        if text == "500 MB":
            return 500
        if text == "1 GB":
            return 1024
        if text == "2 GB":
            return 2048
        return 1024

    def _get_codec_info(self):
        idx = self.cmb_codec.currentIndex()
        return [("hevc_nvenc", True), ("h264_nvenc", True),
                ("hevc", False), ("h264", False)][idx]

    def _start_compress(self):
        input_path = self.txt_input.text().strip()
        if not input_path or not os.path.exists(input_path):
            QMessageBox.warning(self, "提示", "请选择有效的源文件")
            return
        output = self.txt_output.text().strip()
        if not output:
            # 输出为空时，默认使用源文件同目录
            base = os.path.splitext(input_path)[0]
            output = f"{base}_compressed{self._get_output_ext()}"
            self.txt_output.setText(output)
        ff_path = self.config.get("ffmpeg_path", "")
        if not ff_path or not os.path.exists(ff_path):
            QMessageBox.warning(self, "提示", "未找到可用的 FFmpeg")
            return

        if not self.file_info:
            self._probe_file(input_path)
        if not self.file_info or self.file_info["duration"] <= 0:
            QMessageBox.warning(self, "提示", "无法读取文件信息")
            return

        target_mb = self._get_target_size_mb()
        codec, use_nvenc = self._get_codec_info()
        audio_bitrate = self.spn_audio.value()

        ff = FFmpegWrapper(
            self.config.get("ffmpeg_path", ""),
            self.config.get("ffprobe_path", "")
        )
        cmd, info = ff.build_compress_command(
            input_path, output, target_mb,
            self.file_info["duration"],
            codec=codec, use_nvenc=use_nvenc,
            audio_bitrate=audio_bitrate
        )

        self.log.clear()
        self.log.appendPlainText(
            f"目标大小: {target_mb} MB\n"
            f"预计视频码率: {info['video_bitrate']} kbps\n"
            f"预计总码率: {info['total_bitrate']} kbps"
        )
        self._run_worker(cmd, self.file_info["duration"])

    def _run_worker(self, cmd, duration):
        self.worker = FFmpegWorker(cmd, duration)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.btn_compress.setEnabled(False)
        self.btn_compress.setText("处理中...")
        self.btn_cancel.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.worker.start()

    def _cancel_compress(self):
        if self.worker and self.worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("取消中...")
            self.worker.cancel()

    def _on_progress(self, pct):
        self.progress.setValue(pct)

    def _on_log(self, msg):
        self.log.appendPlainText(msg)

    def _on_finished(self, success, msg):
        self.btn_compress.setEnabled(True)
        self.btn_compress.setText("开始压缩")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("取消")
        if success:
            self.progress.setValue(100)
            QMessageBox.information(self, "成功", f"压缩完成\n{msg}")
        else:
            QMessageBox.warning(self, "失败", f"压缩失败\n{msg}")


# ==================== PDF 工具页签 ====================
class PdfTab(QWidget):
    MODE_WORD, MODE_PERM, MODE_WM, MODE_IMG = range(4)

    def __init__(self, config, status_bar, parent=None):
        super().__init__(parent)
        self.config = config
        self.status_bar = status_bar
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("pageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 处理功能：平铺直选卡片 + 对应参数
        mode_group = QGroupBox("处理功能")
        mv = QVBoxLayout(mode_group)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(12)
        self.mode_btns = []
        self.mode_group_box = QButtonGroup(self)
        self.mode_group_box.setExclusive(True)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        for i, name in enumerate(["Word 转 PDF", "PDF 权限限制",
                                  "PDF 文字水印", "PDF 转图片并加水印"]):
            btn = QPushButton(name)
            btn.setObjectName("modeCard")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(44)
            self.mode_group_box.addButton(btn, i)
            cards.addWidget(btn, 1)
            self.mode_btns.append(btn)
        mv.addLayout(cards)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        mv.addWidget(self.stack)
        self.stack.addWidget(self._build_word_page())
        self.stack.addWidget(self._build_perm_page())
        self.stack.addWidget(self._build_wm_page())
        self.stack.addWidget(self._build_img_page())
        layout.addWidget(mode_group)

        # 输入输出（位于功能选择与参数下方）
        io_group = QGroupBox("输入 / 输出")
        g = QGridLayout(io_group)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(12)
        g.addWidget(QLabel("源路径:"), 0, 0)
        self.txt_input = DropLineEdit()
        self.txt_input.setPlaceholderText("可拖入文件或文件夹，文件夹将递归处理")
        self.btn_browse_dir = QPushButton("选目录...")
        self.btn_browse_file = QPushButton("选文件...")
        g.addWidget(self.txt_input, 0, 1)
        g.addWidget(self.btn_browse_dir, 0, 2)
        g.addWidget(self.btn_browse_file, 0, 3)
        g.addWidget(QLabel("输出目录:"), 1, 0)
        self.txt_output = QLineEdit()
        self.btn_browse_out = QPushButton("浏览...")
        g.addWidget(self.txt_output, 1, 1)
        g.addWidget(self.btn_browse_out, 1, 2)
        self.lbl_out_hint = QLabel("")
        self.lbl_out_hint.setObjectName("info")
        self.lbl_out_hint.setWordWrap(True)
        g.addWidget(self.lbl_out_hint, 2, 1, 1, 3)
        g.setColumnStretch(1, 1)
        layout.addWidget(io_group)

        # 开始按钮 + 取消按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_start = QPushButton("开始处理")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(44)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("cancel")
        self.btn_cancel.setMinimumHeight(44)
        self.btn_cancel.setVisible(False)
        btn_row.addWidget(self.btn_start, 1)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        # 进度与日志
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setMaximumHeight(140)
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("处理日志会显示在这里")
        layout.addWidget(self.log)

        # 信号
        self.btn_browse_dir.clicked.connect(self._browse_dir)
        self.btn_browse_file.clicked.connect(self._browse_file)
        self.btn_browse_out.clicked.connect(self._browse_out)
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._cancel)
        self.mode_group_box.idClicked.connect(self._on_mode_changed)
        self.txt_input.file_dropped.connect(
            lambda p: self.txt_input.setText(p))
        self.mode_btns[0].setChecked(True)
        self._on_mode_changed(0)
        _fix_input_heights(content)

        # 内容装入滚动区域，窗口不够高时可滚动，避免卡片被挤压导致控件重叠
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_word_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("需要本机安装 Microsoft Word；自动接受修订并删除批注，"
                      "原 Word 文件不会被修改。输出目录留空时输出到源目录旁的 *_PDF 文件夹")
        hint.setObjectName("info")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(hint)
        v.addStretch()
        return page

    def _build_perm_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel("权限密码:"))
        self.txt_password = QLineEdit()
        self.txt_password.setText("1234567890")
        row.addWidget(self.txt_password, 1)

        v.addLayout(row)
        perms_row = QHBoxLayout()
        perms_row.setSpacing(16)
        perms_row.addWidget(QLabel("允许操作:"))
        self.chk_perm_print = QCheckBox("打印")
        self.chk_perm_copy = QCheckBox("复制内容")
        self.chk_perm_modify = QCheckBox("修改文档")
        self.chk_perm_annot = QCheckBox("批注/表单")
        for c in (self.chk_perm_print, self.chk_perm_copy,
                  self.chk_perm_modify, self.chk_perm_annot):
            perms_row.addWidget(c)
        perms_row.addStretch()
        v.addLayout(perms_row)
        hint = QLabel("未勾选的操作将被禁止，打开 PDF 始终无需密码；"
                      "输出目录留空时将覆盖原文件，建议先备份")
        hint.setObjectName("info")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(hint)
        v.addStretch()
        return page

    def _build_wm_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(12)
        g.addWidget(QLabel("水印文字:"), 0, 0)
        self.txt_wm_text = QLineEdit("示例水印文字")
        g.addWidget(self.txt_wm_text, 0, 1)
        g.addWidget(QLabel("字号:"), 0, 2)
        self.spn_wm_size = QSpinBox()
        self.spn_wm_size.setRange(6, 120)
        self.spn_wm_size.setValue(18)
        g.addWidget(self.spn_wm_size, 0, 3)
        g.addWidget(QLabel("行数:"), 1, 0)
        self.spn_wm_rows = QSpinBox()
        self.spn_wm_rows.setRange(1, 20)
        self.spn_wm_rows.setValue(5)
        g.addWidget(self.spn_wm_rows, 1, 1)
        g.addWidget(QLabel("列数:"), 1, 2)
        self.spn_wm_cols = QSpinBox()
        self.spn_wm_cols.setRange(1, 20)
        self.spn_wm_cols.setValue(3)
        g.addWidget(self.spn_wm_cols, 1, 3)
        g.addWidget(QLabel("角度:"), 2, 0)
        self.spn_wm_angle = QSpinBox()
        self.spn_wm_angle.setRange(0, 90)
        self.spn_wm_angle.setValue(35)
        g.addWidget(self.spn_wm_angle, 2, 1)
        g.addWidget(QLabel("透明度(%):"), 2, 2)
        self.spn_wm_alpha = QSpinBox()
        self.spn_wm_alpha.setRange(5, 100)
        self.spn_wm_alpha.setValue(20)
        g.addWidget(self.spn_wm_alpha, 2, 3)
        hint = QLabel("文字保留可选中，文件体积几乎不变；"
                      "输出目录留空时将覆盖原文件，建议先备份")
        hint.setObjectName("info")
        hint.setWordWrap(True)
        g.addWidget(hint, 3, 0, 1, 4)
        g.setColumnStretch(1, 1)
        return page

    def _build_img_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(12)
        g.addWidget(QLabel("水印文字:"), 0, 0)
        self.txt_img_text = QLineEdit("示例水印文字")
        g.addWidget(self.txt_img_text, 0, 1)
        g.addWidget(QLabel("字号:"), 0, 2)
        self.spn_img_size = QSpinBox()
        self.spn_img_size.setRange(6, 200)
        self.spn_img_size.setValue(36)
        g.addWidget(self.spn_img_size, 0, 3)
        g.addWidget(QLabel("行数:"), 1, 0)
        self.spn_img_rows = QSpinBox()
        self.spn_img_rows.setRange(1, 20)
        self.spn_img_rows.setValue(5)
        g.addWidget(self.spn_img_rows, 1, 1)
        g.addWidget(QLabel("列数:"), 1, 2)
        self.spn_img_cols = QSpinBox()
        self.spn_img_cols.setRange(1, 20)
        self.spn_img_cols.setValue(2)
        g.addWidget(self.spn_img_cols, 1, 3)
        g.addWidget(QLabel("角度:"), 2, 0)
        self.spn_img_angle = QSpinBox()
        self.spn_img_angle.setRange(0, 90)
        self.spn_img_angle.setValue(35)
        g.addWidget(self.spn_img_angle, 2, 1)
        g.addWidget(QLabel("透明度(%):"), 2, 2)
        self.spn_img_alpha = QSpinBox()
        self.spn_img_alpha.setRange(5, 100)
        self.spn_img_alpha.setValue(30)
        g.addWidget(self.spn_img_alpha, 2, 3)
        g.addWidget(QLabel("清晰度:"), 3, 0)
        self.spn_img_quality = QSpinBox()
        self.spn_img_quality.setRange(10, 100)
        self.spn_img_quality.setValue(85)
        g.addWidget(self.spn_img_quality, 3, 1)
        g.addWidget(QLabel("渲染倍率:"), 3, 2)
        self.spn_img_zoom = QDoubleSpinBox()
        self.spn_img_zoom.setRange(1.0, 4.0)
        self.spn_img_zoom.setSingleStep(0.1)
        self.spn_img_zoom.setValue(1.5)
        g.addWidget(self.spn_img_zoom, 3, 3)
        hint = QLabel("每页转为图片后加水印，文字无法选中提取，防止二次编辑；"
                      "输出目录留空时将覆盖原文件，建议先备份")
        hint.setObjectName("info")
        hint.setWordWrap(True)
        g.addWidget(hint, 4, 0, 1, 4)
        g.setColumnStretch(1, 1)
        return page

    def _current_mode(self):
        btn = self.mode_group_box.checkedButton()
        return self.mode_btns.index(btn) if btn else self.MODE_WORD

    def _on_mode_changed(self, idx):
        self.stack.setCurrentIndex(idx)
        hints = {
            self.MODE_WORD: "输出目录留空时，输出到源目录旁的 *_PDF 文件夹",
            self.MODE_PERM: "输出目录留空时，将覆盖原 PDF 文件",
            self.MODE_WM: "输出目录留空时，将覆盖原 PDF 文件",
            self.MODE_IMG: "输出目录留空时，将覆盖原 PDF 文件",
        }
        self.lbl_out_hint.setText(hints.get(idx, ""))

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            self.txt_input.setText(d)

    def _browse_file(self):
        last_dir = self.config.get("last_output_dir", "")
        flt = ("Word 文件 (*.docx *.doc);;所有文件 (*)"
               if self._current_mode() == self.MODE_WORD
               else "PDF 文件 (*.pdf);;所有文件 (*)")
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", last_dir, flt)
        if files:
            self.txt_input.setText(files[0])
            self.config.set("last_output_dir", os.path.dirname(files[0]))

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.txt_output.setText(d)

    def _collect_inputs(self):
        src = self.txt_input.text().strip()
        if not src:
            return []
        return [src]

    def _start(self):
        mode = self._current_mode()
        exts = DOC_EXTS if mode == self.MODE_WORD else PDF_EXTS
        files = collect_files(self._collect_inputs(), exts)
        if not files:
            QMessageBox.warning(self, "提示", "未找到待处理的文件")
            return
        out_dir = self.txt_output.text().strip()

        if mode == self.MODE_WORD:
            task = partial(word_to_pdf, files, out_dir)
            label = "Word 转 PDF"
        elif mode == self.MODE_PERM:
            task = partial(set_pdf_permissions, files, out_dir,
                           self.txt_password.text().strip(),
                           allow_print=self.chk_perm_print.isChecked(),
                           allow_copy=self.chk_perm_copy.isChecked(),
                           allow_modify=self.chk_perm_modify.isChecked(),
                           allow_annotate=self.chk_perm_annot.isChecked())
            label = "PDF 权限设置"
        elif mode == self.MODE_WM:
            task = partial(
                add_text_watermark, files, out_dir,
                text=self.txt_wm_text.text().strip() or "水印",
                font=font_path(), rows=self.spn_wm_rows.value(),
                cols=self.spn_wm_cols.value(),
                font_size=self.spn_wm_size.value(),
                opacity=self.spn_wm_alpha.value() / 100,
                angle=self.spn_wm_angle.value())
            label = "PDF 文字水印"
        else:
            task = partial(
                convert_to_image_pdf, files, out_dir,
                text=self.txt_img_text.text().strip() or "水印",
                font=font_path(), rows=self.spn_img_rows.value(),
                cols=self.spn_img_cols.value(),
                font_size=self.spn_img_size.value(),
                opacity=self.spn_img_alpha.value() / 100,
                angle=self.spn_img_angle.value(),
                zoom=self.spn_img_zoom.value(),
                quality=self.spn_img_quality.value())
            label = "PDF 转图片并加水印"

        self.worker = PdfWorker(task, label)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.finished_signal.connect(self._on_finished)
        self.btn_start.setEnabled(False)
        self.btn_start.setText("处理中...")
        self.btn_cancel.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log.clear()
        self.log.appendPlainText(f"{label}，共 {len(files)} 个文件")
        self.worker.start()

    def _cancel(self):
        if self.worker and self.worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("取消中...")
            self.worker.cancel()

    def _on_finished(self, success, msg):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("开始处理")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("取消")
        if success:
            self.progress.setValue(100)
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)


# ==================== 视频水印页签 ====================
class WatermarkTab(QWidget):
    def __init__(self, config, status_bar, parent=None):
        super().__init__(parent)
        self.config = config
        self.status_bar = status_bar
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("pageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 文件卡片
        file_group = QGroupBox("文件列表")
        f_layout = QVBoxLayout(file_group)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.btn_add = QPushButton("＋ 添加文件")
        self.btn_add_dir = QPushButton("＋ 添加目录")
        self.btn_remove = QPushButton("－ 删除选中")
        self.btn_clear = QPushButton("× 清空")
        for btn in (self.btn_add, self.btn_add_dir, self.btn_remove,
                    self.btn_clear):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        f_layout.addLayout(toolbar)

        hint = QLabel("拖入视频即可添加；已加水印的文件可自动跳过")
        hint.setObjectName("info")
        f_layout.addWidget(hint)

        # 文件列表
        self.file_list = FileListWidget(
            empty_text="拖拽视频到此处\n或点击「添加文件」")
        self.file_list.setMinimumHeight(200)
        f_layout.addWidget(self.file_list, 1)
        layout.addWidget(file_group)

        # 参数
        params = QGroupBox("水印设置")
        g = QGridLayout(params)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(12)
        g.addWidget(QLabel("水印文字:"), 0, 0)
        self.txt_text = QLineEdit("示例水印文字")
        g.addWidget(self.txt_text, 0, 1)
        g.addWidget(QLabel("颜色:"), 0, 2)
        self.txt_color = QLineEdit("#FF0000")
        g.addWidget(self.txt_color, 0, 3)
        g.addWidget(QLabel("字号:"), 1, 0)
        self.spn_size = QSpinBox()
        self.spn_size.setRange(8, 200)
        self.spn_size.setValue(40)
        g.addWidget(self.spn_size, 1, 1)
        g.addWidget(QLabel("透明度(%):"), 1, 2)
        self.spn_alpha = QSpinBox()
        self.spn_alpha.setRange(5, 100)
        self.spn_alpha.setValue(30)
        g.addWidget(self.spn_alpha, 1, 3)
        g.addWidget(QLabel("出现频率:"), 2, 0)
        self.spn_freq = QSpinBox()
        self.spn_freq.setRange(1, 30)
        self.spn_freq.setValue(7)
        g.addWidget(self.spn_freq, 2, 1)
        g.addWidget(QLabel("视频码率:"), 2, 2)
        self.spn_bitrate = QSpinBox()
        self.spn_bitrate.setRange(500, 50000)
        self.spn_bitrate.setValue(2000)
        self.spn_bitrate.setSuffix(" kbps")
        g.addWidget(self.spn_bitrate, 2, 3)
        self.chk_skip = QCheckBox("跳过已加水印的视频（按元数据标记识别）")
        self.chk_skip.setChecked(True)
        g.addWidget(self.chk_skip, 3, 0, 1, 2)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("输出方式:"))
        self.cmb_output = QComboBox()
        self.cmb_output.addItems(["替换原文件", "另存为新文件"])
        row.addWidget(self.cmb_output)
        row.addStretch()
        g.addLayout(row, 3, 2, 1, 2)
        g.setColumnStretch(1, 1)
        layout.addWidget(params)

        # 开始按钮 + 取消按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_start = QPushButton("开始加水印")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(44)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("cancel")
        self.btn_cancel.setMinimumHeight(44)
        self.btn_cancel.setVisible(False)
        btn_row.addWidget(self.btn_start, 1)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        # 进度与日志
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setMaximumHeight(140)
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("处理日志会显示在这里")
        layout.addWidget(self.log)

        # 信号
        self.btn_add.clicked.connect(self._add_files)
        self.btn_add_dir.clicked.connect(self._add_dir)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self.file_list.clear)
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._cancel)
        self.file_list.files_dropped.connect(self._add_paths)
        _fix_input_heights(content)

        # 内容装入滚动区域，窗口不够高时可滚动，避免卡片被挤压导致控件重叠
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _add_files(self):
        last_dir = self.config.get("last_output_dir", "")
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", last_dir,
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.flv *.ts *.wmv);;所有文件 (*)")
        if files:
            self._add_paths(files)
            self.config.set("last_output_dir", os.path.dirname(files[0]))

    def _add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择目录（递归扫描视频）")
        if d:
            self._add_paths([d])

    def _add_paths(self, paths):
        existing = {self.file_list.item(i).data(Qt.UserRole)
                    for i in range(self.file_list.count())}
        for f in collect_videos(paths):
            if f in existing:
                continue
            item = QListWidgetItem(f"{os.path.basename(f)}")
            item.setData(Qt.UserRole, f)
            self.file_list.addItem(item)

    def _remove_selected(self):
        for item in reversed(self.file_list.selectedItems()):
            self.file_list.takeItem(self.file_list.row(item))

    def _start(self):
        files = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        if not files:
            QMessageBox.warning(self, "提示", "请先添加视频文件")
            return
        ffmpeg = self.config.get("ffmpeg_path", "")
        ffprobe = self.config.get("ffprobe_path", "")
        if not ffmpeg or not os.path.exists(ffmpeg):
            QMessageBox.warning(self, "提示", "未找到可用的 FFmpeg")
            return

        as_new = self.cmb_output.currentIndex() == 1
        jobs = []
        skipped = 0
        for f in files:
            probe = probe_video(ffprobe, f)
            if not probe:
                self.log.appendPlainText(f"✗ 无法读取，跳过: {f}")
                skipped += 1
                continue
            if self.chk_skip.isChecked() and is_marked(probe):
                self.log.appendPlainText(f"– 已加水印，跳过: {f}")
                skipped += 1
                continue
            temp = suggest_output(f, as_new)
            cmd, dur = build_command(
                ffmpeg, f, temp, font_path(), probe,
                text=self.txt_text.text().strip() or "水印",
                color=self.txt_color.text().strip() or "#FF0000",
                fontsize=self.spn_size.value(),
                alpha=self.spn_alpha.value() / 100,
                frequency_factor=self.spn_freq.value(),
                video_bitrate_k=self.spn_bitrate.value(),
                codec=self.config.get("default_codec", "hevc_nvenc"),
                use_nvenc=self.config.get("use_nvenc", True),
            )
            jobs.append((f, temp, not as_new, cmd, dur))

        if not jobs:
            QMessageBox.information(
                self, "提示", "没有需要处理的文件"
                + (f"（跳过 {skipped} 个）" if skipped else ""))
            return

        if not as_new:
            ret = QMessageBox.question(
                self, "确认",
                f"将替换 {len(jobs)} 个原视频文件（不可恢复），是否继续？",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return

        self.worker = VideoWatermarkWorker(jobs)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.file_progress.connect(
            lambda pct: self.status_bar.showMessage(f"当前文件进度 {pct}%"))
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.finished_signal.connect(self._on_finished)
        self.btn_start.setEnabled(False)
        self.btn_start.setText("处理中...")
        self.btn_cancel.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log.clear()
        self.log.appendPlainText(f"共 {len(jobs)} 个文件待处理"
                                 + (f"，跳过 {skipped} 个" if skipped else ""))
        self.worker.start()

    def _cancel(self):
        if self.worker and self.worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("取消中...")
            self.worker.cancel()

    def _on_finished(self, success, msg):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("开始加水印")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("取消")
        self.status_bar.showMessage("")
        if success:
            self.progress.setValue(100)
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)


# ==================== 设置页签 ====================
class SettingsTab(QWidget):
    theme_changed = pyqtSignal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("pageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        appear = QGroupBox("外观")
        a_layout = QGridLayout(appear)
        a_layout.setContentsMargins(0, 0, 0, 0)
        a_layout.setHorizontalSpacing(12)
        a_layout.setVerticalSpacing(12)
        a_layout.addWidget(QLabel("界面主题:"), 0, 0)
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["浅色", "深色"])
        a_layout.addWidget(self.cmb_theme, 0, 1)
        a_layout.setColumnStretch(1, 1)
        layout.addWidget(appear)

        # 默认设置
        defaults_group = QGroupBox("默认设置")
        d_layout = QGridLayout(defaults_group)
        d_layout.setContentsMargins(0, 0, 0, 0)
        d_layout.setHorizontalSpacing(12)
        d_layout.setVerticalSpacing(12)
        d_layout.addWidget(QLabel("默认视频编码:"), 0, 0)
        self.cmb_codec = QComboBox()
        self.cmb_codec.addItems(["HEVC NVENC", "H.264 NVENC", "HEVC 软解", "H.264 软解"])
        d_layout.addWidget(self.cmb_codec, 0, 1)
        d_layout.addWidget(QLabel("默认音频码率:"), 1, 0)
        self.spn_audio = QSpinBox()
        self.spn_audio.setRange(32, 512)
        self.spn_audio.setValue(128)
        self.spn_audio.setSuffix(" kbps")
        d_layout.addWidget(self.spn_audio, 1, 1)
        self.chk_nvenc = QCheckBox("默认使用 NVENC 硬件加速")
        d_layout.addWidget(self.chk_nvenc, 2, 0, 1, 2)
        d_layout.setColumnStretch(1, 1)
        layout.addWidget(defaults_group)

        # 运行状态
        status_group = QGroupBox("运行状态")
        s_layout = QVBoxLayout(status_group)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(10)
        self.lbl_nvenc = QLabel()
        self.lbl_nvenc.setObjectName("info")
        s_layout.addWidget(self.lbl_nvenc)
        hint = QLabel("程序已内置 FFmpeg，无需配置。"
                      "如需更换版本，可将 ffmpeg.exe / ffprobe.exe "
                      "放入程序同目录的 ffmpeg_bin 文件夹")
        hint.setObjectName("info")
        hint.setWordWrap(True)
        s_layout.addWidget(hint)
        layout.addWidget(status_group)

        # 保存
        self.btn_save = QPushButton("保存设置")
        self.btn_save.setObjectName("primary")
        self.btn_save.setMinimumHeight(44)
        layout.addWidget(self.btn_save)
        layout.addStretch()

        # 信号
        self.btn_save.clicked.connect(self._save)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_combo)

        # 内容装入滚动区域后，再统一输入控件高度
        scroll.setWidget(content)
        outer.addWidget(scroll)
        _fix_input_heights(self)

    def _check_nvenc(self):
        ff = FFmpegWrapper(
            self.config.get("ffmpeg_path", ""),
            self.config.get("ffprobe_path", "")
        )
        if not ff.ffmpeg or not os.path.exists(ff.ffmpeg):
            self.lbl_nvenc.setText("✗ 未找到 FFmpeg")
            self.lbl_nvenc.setObjectName("error")
        elif ff.check_nvenc():
            self.lbl_nvenc.setText("✓ NVENC 硬件加速可用")
            self.lbl_nvenc.setObjectName("success")
        else:
            self.lbl_nvenc.setText("✗ NVENC 不可用")
            self.lbl_nvenc.setObjectName("error")
        self.style().unpolish(self.lbl_nvenc)
        self.style().polish(self.lbl_nvenc)

    def _load_settings(self):
        codec = self.config.get("default_codec", "hevc_nvenc")
        codec_map = {"hevc_nvenc": 0, "h264_nvenc": 1, "hevc": 2, "h264": 3}
        self.cmb_codec.setCurrentIndex(codec_map.get(codec, 0))
        self.spn_audio.setValue(self.config.get("default_audio_bitrate", 128))
        self.chk_nvenc.setChecked(self.config.get("use_nvenc", True))
        self.sync_theme(self.config.get("theme", "light"))
        self._check_nvenc()

    def sync_theme(self, name):
        self.cmb_theme.blockSignals(True)
        self.cmb_theme.setCurrentIndex(0 if name != "dark" else 1)
        self.cmb_theme.blockSignals(False)

    def _on_theme_combo(self, idx):
        self.theme_changed.emit("light" if idx == 0 else "dark")

    def _save(self):
        codec_map = {0: "hevc_nvenc", 1: "h264_nvenc", 2: "hevc", 3: "h264"}
        self.config.set("default_codec", codec_map.get(self.cmb_codec.currentIndex(), "hevc_nvenc"))
        self.config.set("default_audio_bitrate", self.spn_audio.value())
        self.config.set("use_nvenc", self.chk_nvenc.isChecked())
        QMessageBox.information(self, "成功", "设置已保存")


# ==================== 左侧导航 ====================
class NavRail(QWidget):
    page_changed = pyqtSignal(int)
    theme_toggled = pyqtSignal()

    def __init__(self, icons, parent=None):
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(208)
        self._nav_keys = [
            "__NAV_MERGE__", "__NAV_COMPRESS__",
            "__NAV_WATERMARK__", "__NAV_PDF__", "__NAV_SETTINGS__",
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 22, 14, 16)
        layout.setSpacing(4)

        brand = QLabel(APP_NAME)
        brand.setObjectName("brandTitle")
        sub = QLabel(APP_TAGLINE)
        sub.setObjectName("brandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(18)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        labels = ["合并视频", "压缩视频", "视频水印", "PDF 工具"]
        self._nav_btns = []
        for i, text in enumerate(labels):
            btn = self._make_item(icons.get(self._nav_keys[i], ""), text)
            self.group.addButton(btn, i)
            self._nav_btns.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)
        btn_set = self._make_item(icons.get("__NAV_SETTINGS__", ""), "设置")
        self.group.addButton(btn_set, 4)
        self._nav_btns.append(btn_set)
        layout.addWidget(btn_set)

        self.btn_theme = QPushButton("切换为深色")
        self.btn_theme.setObjectName("themeToggle")
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.clicked.connect(self.theme_toggled.emit)
        layout.addWidget(self.btn_theme)

        self.lbl_ff = QLabel()
        self.lbl_ff.setObjectName("navStatus")
        self.lbl_ff.setWordWrap(True)
        layout.addWidget(self.lbl_ff)

        self.group.button(0).setChecked(True)
        self.group.buttonClicked.connect(
            lambda btn: self.page_changed.emit(self.group.id(btn)))

    def _make_item(self, icon_path, text):
        btn = QPushButton("  " + text)
        btn.setObjectName("navItem")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if icon_path:
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(16, 16))
        return btn

    def refresh_icons(self, icons):
        for btn, key in zip(self._nav_btns, self._nav_keys):
            path = icons.get(key, "")
            if path:
                btn.setIcon(QIcon(path))

    def set_theme_label(self, name):
        if name == "dark":
            self.btn_theme.setText("切换为浅色")
        else:
            self.btn_theme.setText("切换为深色")

    def set_ffmpeg_status(self, ok):
        if ok:
            self.lbl_ff.setText("FFmpeg 已就绪")
        else:
            self.lbl_ff.setText("未找到 FFmpeg")


# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self._theme = self.config.get("theme", "light")
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(920, 680)
        self.resize(1040, 760)

        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.jpg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        root = QWidget()
        root.setObjectName("pageContent")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.nav = NavRail(UI_ICONS)
        self.stack = QStackedWidget()
        self.merge_tab = MergeTab(self.config, self.statusBar())
        self.compress_tab = CompressTab(self.config, self.statusBar())
        self.watermark_tab = WatermarkTab(self.config, self.statusBar())
        self.pdf_tab = PdfTab(self.config, self.statusBar())
        self.settings_tab = SettingsTab(self.config)
        for page in (self.merge_tab, self.compress_tab, self.watermark_tab,
                     self.pdf_tab, self.settings_tab):
            self.stack.addWidget(page)

        h.addWidget(self.nav)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.nav.page_changed.connect(self.stack.setCurrentIndex)
        self.nav.theme_toggled.connect(self._toggle_theme)
        self.settings_tab.theme_changed.connect(self.set_theme)
        self.nav.set_theme_label(self._theme)

        ff_path = self.config.get("ffmpeg_path", "")
        ff_ok = bool(ff_path and os.path.exists(ff_path))
        self.nav.set_ffmpeg_status(ff_ok)
        if ff_ok:
            self.statusBar().showMessage("就绪")
        else:
            self.statusBar().showMessage("未找到可用的 FFmpeg")

    def _toggle_theme(self):
        self.set_theme("light" if self._theme == "dark" else "dark")

    def set_theme(self, name, persist=True):
        app = QApplication.instance()
        name, icons = apply_app_theme(app, name)
        self._theme = name
        self.nav.refresh_icons(icons)
        self.nav.set_theme_label(name)
        self.settings_tab.sync_theme(name)
        if persist:
            self.config.set("theme", name)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    config = Config()
    apply_app_theme(app, config.get("theme", "light"))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
