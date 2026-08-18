import sys
import os

# 必须在导入 PyQt5 之前设置
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QComboBox, QSpinBox, QCheckBox, QProgressBar, QPlainTextEdit, QGroupBox,
    QFileDialog, QMessageBox, QAbstractItemView, QStatusBar, QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QPalette, QColor

from config import Config
from ffmpeg_core import FFmpegWrapper, FileSorter, FFmpegWorker


def _fix_input_heights(widget):
    """QSS 的 min-height 不参与布局计算，会导致控件重叠，
    这里统一用固定高度，保证行距正常。"""
    for w in widget.findChildren((QLineEdit, QComboBox, QSpinBox)):
        w.setFixedHeight(40)


# ==================== 现代浅色主题 ====================
STYLE_SHEET = """
/* === 基础 === */
QMainWindow {
    background-color: #f1f5f9;
}
QWidget {
    color: #1e293b;
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 14px;
}
/* === Tab 导航 === */
QTabWidget::pane {
    border: none;
    top: 0px;
    background-color: #f1f5f9;
}
QTabBar {
    background-color: #e2e8f0;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 4px;
}
QTabBar::tab {
    background-color: transparent;
    color: #64748b;
    padding: 10px 28px;
    border: none;
    border-radius: 10px;
    margin-right: 4px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #4f46e5;
    font-weight: 600;
    border: 1px solid #cbd5e1;
}
QTabBar::tab:hover:!selected {
    background-color: rgba(255, 255, 255, 0.5);
    color: #334155;
}

/* === 按钮 === */
QPushButton {
    background-color: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    padding: 8px 18px;
    border-radius: 10px;
    min-height: 24px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
}
QPushButton:pressed {
    background-color: #e2e8f0;
    border-color: #94a3b8;
    color: #475569;
}
QPushButton:disabled {
    background-color: #f1f5f9;
    color: #94a3b8;
    border-color: #e2e8f0;
}
QPushButton#primary {
    background-color: #4f46e5;
    color: #ffffff;
    border: none;
    font-weight: 600;
}
QPushButton#primary:hover {
    background-color: #5b54e6;
}
QPushButton#primary:pressed {
    background-color: #4338ca;
}
QPushButton#primary:disabled {
    background-color: #a5b4fc;
    color: #ffffff;
}
QPushButton#cancel {
    background-color: #ffffff;
    color: #dc2626;
    border: 1px solid #fca5a5;
    font-weight: 500;
}
QPushButton#cancel:hover {
    background-color: #fef2f2;
    border-color: #f87171;
}
QPushButton#cancel:pressed {
    background-color: #fee2e2;
    color: #b91c1c;
}

/* === 列表 === */
QListWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 8px;
    outline: none;
}
QListWidget::item {
    padding: 12px 14px;
    border-radius: 10px;
    color: #334155;
    margin: 3px 0px;
}
QListWidget::item:selected {
    background-color: #e0e7ff;
    color: #4f46e5;
    border: 1px solid #c7d2fe;
}
QListWidget::item:hover:!selected {
    background-color: #f8fafc;
}

/* === 输入框 === */
QLineEdit, QSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    padding: 0px 14px;
    color: #1e293b;
    selection-background-color: #a5b4fc;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #6366f1;
    background-color: #ffffff;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: #94a3b8;
    border-color: #e2e8f0;
    background-color: #f8fafc;
}

/* === 下拉框 === */
QComboBox::drop-down {
    border: none;
    width: 32px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #64748b;
}
QComboBox:focus::down-arrow {
    border-top-color: #4f46e5;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    color: #334155;
    selection-background-color: #e0e7ff;
    selection-color: #4f46e5;
    outline: none;
    padding: 6px;
}
QComboBox QAbstractItemView::item {
    padding: 10px 14px;
    border-radius: 8px;
    min-height: 22px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #f8fafc;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #e0e7ff;
    color: #4f46e5;
}

QSpinBox {
    padding-right: 30px;
}

/* === 数字框箭头 === */
QSpinBox::up-button, QSpinBox::down-button {
    background-color: transparent;
    border: none;
    width: 24px;
    height: 18px;
}
QSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
}
QSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
}
QSpinBox::up-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #64748b;
}
QSpinBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748b;
}

/* === 进度条 === */
QProgressBar {
    background-color: #e2e8f0;
    border: none;
    border-radius: 10px;
    text-align: center;
    color: #1e293b;
    min-height: 28px;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: #4f46e5;
    border-radius: 10px;
}

/* === 日志框 === */
QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    color: #475569;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 13px;
    padding: 10px;
}

/* === 分组框 === */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    margin-top: 12px;
    padding-top: 44px;
    padding-bottom: 16px;
    padding-left: 16px;
    padding-right: 16px;
    color: #1e293b;
    font-weight: 600;
    font-size: 15px;
}
QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    top: 12px;
    left: 14px;
    background-color: transparent;
    color: #475569;
    font-size: 15px;
    font-weight: 700;
}

/* === 滚动区域 === */
QScrollArea {
    background-color: #f1f5f9;
    border: none;
}
QScrollArea > QWidget {
    background-color: #f1f5f9;
}
QWidget#pageContent {
    background-color: #f1f5f9;
}

/* === 复选框 === */
QCheckBox {
    color: #334155;
    spacing: 10px;
    padding: 4px 0px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #cbd5e1;
    background-color: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #4f46e5;
    border-color: #4f46e5;
}
QCheckBox::indicator:hover {
    border-color: #94a3b8;
}

/* === 标签状态色 === */
QLabel#info { color: #64748b; }
QLabel#success { color: #16a34a; font-weight: 600; }
QLabel#warning { color: #d97706; font-weight: 600; }
QLabel#error { color: #dc2626; font-weight: 600; }

/* === 状态栏 === */
QStatusBar {
    background-color: #ffffff;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
    padding: 6px 16px;
    font-size: 13px;
}

/* === 滚动条 === */
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    border: none;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background-color: #cbd5e1;
    border-radius: 5px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background-color: #94a3b8;
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
    background-color: #cbd5e1;
    border-radius: 5px;
    min-width: 40px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #94a3b8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* === 工具提示 === */
QToolTip {
    background-color: #1e293b;
    color: #f8fafc;
    border: none;
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
}

/* === 菜单 === */
QMenu {
    background-color: #ffffff;
    color: #334155;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 8px;
}
QMenu::item {
    padding: 10px 28px;
    border-radius: 8px;
}
QMenu::item:selected {
    background-color: #e0e7ff;
    color: #4f46e5;
}
"""


# ==================== 自定义控件 ====================
class FileListWidget(QListWidget):
    """支持外部文件拖放和内部拖拽排序的列表控件"""
    files_dropped = pyqtSignal(list)
    reordered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

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
        layout.addLayout(toolbar)

        # 提示
        hint = QLabel("✦ 提示: 拖拽文件到列表可添加，列表内拖拽可调整顺序")
        hint.setObjectName("info")
        layout.addWidget(hint)

        # 文件列表
        self.file_list = FileListWidget()
        self.file_list.setMinimumHeight(240)
        layout.addWidget(self.file_list, 1)

        # 输出文件
        out_layout = QHBoxLayout()
        out_layout.setSpacing(10)
        out_layout.addWidget(QLabel("输出文件:"))
        self.txt_output = QLineEdit()
        self.btn_browse_out = QPushButton("浏览...")
        out_layout.addWidget(self.txt_output, 1)
        out_layout.addWidget(self.btn_browse_out)
        layout.addLayout(out_layout)

        # 选项
        opt_layout = QHBoxLayout()
        self.chk_reencode = QCheckBox("编码不一致时重编码合并")
        self.chk_reencode.setChecked(True)
        opt_layout.addWidget(self.chk_reencode)
        opt_layout.addStretch()
        layout.addLayout(opt_layout)

        # 状态
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("info")
        layout.addWidget(self.lbl_status)

        # 开始按钮 + 取消按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_merge = QPushButton("▶ 开始合并")
        self.btn_merge.setObjectName("primary")
        self.btn_merge.setMinimumHeight(44)
        self.btn_cancel = QPushButton("✖ 取消")
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
        self.log.setMaximumHeight(160)
        self.log.setReadOnly(True)
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
            self.lbl_status.setText("⚠ 未配置 FFprobe 路径，无法检查编码")
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
            QMessageBox.warning(self, "提示", "请在设置中配置 FFmpeg 路径")
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
        self.btn_merge.setText("▶ 开始合并")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("✖ 取消")
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
        file_group = QGroupBox("📁 文件")
        file_layout = QGridLayout(file_group)
        file_layout.setContentsMargins(16, 4, 16, 16)
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
        settings_group = QGroupBox("⚙ 压缩设置")
        s_layout = QGridLayout(settings_group)
        s_layout.setContentsMargins(16, 4, 16, 16)
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
        info_group = QGroupBox("ℹ 文件信息")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(16, 4, 16, 16)
        self.lbl_info = QLabel("请选择源文件")
        self.lbl_info.setObjectName("info")
        info_layout.addWidget(self.lbl_info)
        layout.addWidget(info_group)

        # 开始按钮 + 取消按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_compress = QPushButton("▶ 开始压缩")
        self.btn_compress.setObjectName("primary")
        self.btn_compress.setMinimumHeight(44)
        self.btn_cancel = QPushButton("✖ 取消")
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
        self.log.setMaximumHeight(160)
        self.log.setReadOnly(True)
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
            self.lbl_info.setText("无法读取文件信息，请检查 FFprobe 路径")
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
            QMessageBox.warning(self, "提示", "请在设置中配置 FFmpeg 路径")
            return

        if not self.file_info:
            self._probe_file(input_path)
        if not self.file_info or self.file_info["duration"] <= 0:
            QMessageBox.warning(self, "提示", "无法读取文件信息，请检查 FFprobe 路径")
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
        self.btn_compress.setText("▶ 开始压缩")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("✖ 取消")
        if success:
            self.progress.setValue(100)
            QMessageBox.information(self, "成功", f"压缩完成\n{msg}")
        else:
            QMessageBox.warning(self, "失败", f"压缩失败\n{msg}")


# ==================== 设置页签 ====================
class SettingsTab(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # FFmpeg 路径
        path_group = QGroupBox("🔧 FFmpeg 路径")
        p_layout = QGridLayout(path_group)
        p_layout.setContentsMargins(16, 4, 16, 16)
        p_layout.setHorizontalSpacing(12)
        p_layout.setVerticalSpacing(12)
        p_layout.addWidget(QLabel("FFmpeg:"), 0, 0)
        self.txt_ffmpeg = QLineEdit()
        self.btn_ffmpeg = QPushButton("浏览...")
        self.btn_detect = QPushButton("✦ 自动检测")
        p_layout.addWidget(self.txt_ffmpeg, 0, 1)
        p_layout.addWidget(self.btn_ffmpeg, 0, 2)
        p_layout.addWidget(self.btn_detect, 0, 3)
        p_layout.addWidget(QLabel("FFprobe:"), 1, 0)
        self.txt_ffprobe = QLineEdit()
        self.btn_ffprobe = QPushButton("浏览...")
        p_layout.addWidget(self.txt_ffprobe, 1, 1)
        p_layout.addWidget(self.btn_ffprobe, 1, 2)
        p_layout.setColumnStretch(1, 1)
        layout.addWidget(path_group)

        # 默认设置
        defaults_group = QGroupBox("🎛 默认设置")
        d_layout = QGridLayout(defaults_group)
        d_layout.setContentsMargins(16, 4, 16, 16)
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

        # NVENC 状态
        self.lbl_nvenc = QLabel()
        self.lbl_nvenc.setObjectName("info")
        layout.addWidget(self.lbl_nvenc)

        # 保存
        self.btn_save = QPushButton("💾 保存设置")
        self.btn_save.setObjectName("primary")
        self.btn_save.setMinimumHeight(44)
        layout.addWidget(self.btn_save)
        layout.addStretch()

        # 信号
        self.btn_ffmpeg.clicked.connect(lambda: self._browse("txt_ffmpeg", "ffmpeg.exe"))
        self.btn_ffprobe.clicked.connect(lambda: self._browse("txt_ffprobe", "ffprobe.exe"))
        self.btn_detect.clicked.connect(self._auto_detect)
        self.btn_save.clicked.connect(self._save)
        _fix_input_heights(self)

    def _browse(self, attr, name):
        path, _ = QFileDialog.getOpenFileName(
            self, f"选择 {name}", "", f"可执行文件 ({name});;所有文件 (*)"
        )
        if path:
            getattr(self, attr).setText(path)
            self._check_nvenc()

    def _auto_detect(self):
        ffmpeg, ffprobe = Config._auto_detect()
        if ffmpeg:
            self.txt_ffmpeg.setText(ffmpeg)
        if ffprobe:
            self.txt_ffprobe.setText(ffprobe)
        if not ffmpeg:
            QMessageBox.warning(self, "提示", "未找到 FFmpeg，请手动选择路径")
        self._check_nvenc()

    def _check_nvenc(self):
        ff = FFmpegWrapper(self.txt_ffmpeg.text(), self.txt_ffprobe.text())
        if ff.check_nvenc():
            self.lbl_nvenc.setText("✓ NVENC 硬件加速可用")
            self.lbl_nvenc.setObjectName("success")
        else:
            self.lbl_nvenc.setText("✗ NVENC 不可用")
            self.lbl_nvenc.setObjectName("error")
        self.style().unpolish(self.lbl_nvenc)
        self.style().polish(self.lbl_nvenc)

    def _load_settings(self):
        self.txt_ffmpeg.setText(self.config.get("ffmpeg_path", ""))
        self.txt_ffprobe.setText(self.config.get("ffprobe_path", ""))
        codec = self.config.get("default_codec", "hevc_nvenc")
        codec_map = {"hevc_nvenc": 0, "h264_nvenc": 1, "hevc": 2, "h264": 3}
        self.cmb_codec.setCurrentIndex(codec_map.get(codec, 0))
        self.spn_audio.setValue(self.config.get("default_audio_bitrate", 128))
        self.chk_nvenc.setChecked(self.config.get("use_nvenc", True))
        self._check_nvenc()

    def _save(self):
        codec_map = {0: "hevc_nvenc", 1: "h264_nvenc", 2: "hevc", 3: "h264"}
        self.config.set("ffmpeg_path", self.txt_ffmpeg.text())
        self.config.set("ffprobe_path", self.txt_ffprobe.text())
        self.config.set("default_codec", codec_map.get(self.cmb_codec.currentIndex(), "hevc_nvenc"))
        self.config.set("default_audio_bitrate", self.spn_audio.value())
        self.config.set("use_nvenc", self.chk_nvenc.isChecked())
        QMessageBox.information(self, "成功", "设置已保存")


# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.setWindowTitle("视频工具箱 · FFmpeg Video Tool")
        self.setMinimumSize(780, 680)
        self.resize(880, 760)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self.merge_tab = MergeTab(self.config, self.statusBar())
        self.compress_tab = CompressTab(self.config, self.statusBar())
        self.settings_tab = SettingsTab(self.config)
        tabs.addTab(self.merge_tab, "🎬 合并视频")
        tabs.addTab(self.compress_tab, "📦 压缩视频")
        tabs.addTab(self.settings_tab, "⚙ 设置")
        self.setCentralWidget(tabs)

        ff_path = self.config.get("ffmpeg_path", "")
        if not ff_path or not os.path.exists(ff_path):
            self.statusBar().showMessage("⚠ 请在设置中配置 FFmpeg 路径")
        else:
            self.statusBar().showMessage("就绪")


def main():
    # 高 DPI 缩放支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    # 浅色调色板，保证未样式化的原生区域也是浅色
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor("#f1f5f9"))
    pal.setColor(QPalette.WindowText, QColor("#1e293b"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#f8fafc"))
    pal.setColor(QPalette.ToolTipBase, QColor("#1e293b"))
    pal.setColor(QPalette.ToolTipText, QColor("#f8fafc"))
    pal.setColor(QPalette.Text, QColor("#1e293b"))
    pal.setColor(QPalette.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ButtonText, QColor("#334155"))
    pal.setColor(QPalette.Highlight, QColor("#4f46e5"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor("#94a3b8"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
