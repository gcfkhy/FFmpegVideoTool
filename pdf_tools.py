# -*- coding: utf-8 -*-
"""PDF/Word 批量处理核心逻辑。

移植自 D:\\word转pdf 旧脚本（保持原功能不变），并做以下优化：
- 面向 GUI：进度回调、取消支持、日志回调
- Word 转 PDF 不再修改/保存用户的 Word 原文件（旧脚本会 Save 覆盖原文件），
  修订/批注仅在内存中处理后直接导出 PDF；同一 Word 实例复用，速度更快
- PDF 文字水印画布改用页面实际尺寸（旧脚本固定 letter 尺寸，非 Letter 页面会错位）
- 合并旧"PDF转图片+水印"两个重复实现为一个，全部在内存中处理，不再写临时图片文件
- 移除 eval()、python-docx、docx2pdf、pikepdf 等依赖
"""
import os
import io
import sys

from PyQt5.QtCore import QThread, pyqtSignal

try:  # 新版 PyMuPDF
    import pymupdf as fitz
except ImportError:
    import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image, ImageDraw, ImageFont

DOC_EXTS = (".docx", ".doc")
PDF_EXTS = (".pdf",)


class OperationCancelled(Exception):
    """用户取消操作"""


def app_dir():
    """exe 所在目录；开发模式下为源码目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def font_path():
    """内置的 msyh.ttc 字体绝对路径（随包分发）"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or app_dir()
    else:
        base = app_dir()
    return os.path.join(base, "msyh.ttc")


def _ensure_pywin32():
    """开发模式下补齐 pywin32 的 --target 安装布局，打包后无需处理"""
    if getattr(sys, "frozen", False):
        return
    root = app_dir()
    for sub, add_to_path in (
        (os.path.join(root, "pip_tmp", "pywin32_system32"), True),
        (os.path.join(root, "pip_tmp", "win32"), False),
        (os.path.join(root, "pip_tmp", "win32", "lib"), False),
    ):
        if not os.path.isdir(sub):
            continue
        if add_to_path:
            os.environ["PATH"] = sub + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(sub)
            except Exception:
                pass
        if sub not in sys.path:
            sys.path.insert(0, sub)


def collect_files(paths, exts):
    """收集文件：paths 中的目录会递归扫描，文件直接保留"""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                for name in sorted(names):
                    if name.lower().endswith(exts):
                        files.append(os.path.join(root, name))
        elif os.path.isfile(p) and p.lower().endswith(exts):
            files.append(p)
    # 去重并保持顺序
    seen = set()
    unique = []
    for f in files:
        key = os.path.normcase(os.path.abspath(f))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def compute_output(file, base_dir, out_dir, dir_suffix="", ext=None, in_place=True):
    """计算输出路径。

    - 指定 out_dir 时：保持相对 base_dir 的目录结构（无 base_dir 则直接放 out_dir 下）
    - 未指定 out_dir 时：dir_suffix 非空则输出到 源目录+dir_suffix，
      否则按 in_place 覆盖原文件
    """
    stem = os.path.splitext(os.path.basename(file))[0]
    ext = ext or os.path.splitext(file)[1]
    if out_dir:
        if base_dir:
            rel_dir = os.path.relpath(os.path.dirname(file), base_dir)
            target_dir = os.path.join(out_dir, rel_dir)
        else:
            target_dir = out_dir
        return os.path.join(target_dir, stem + ext)
    if dir_suffix:
        return os.path.join(os.path.dirname(file) + dir_suffix, stem + ext)
    if in_place:
        return file
    return os.path.join(os.path.dirname(file), stem + ext)


# ==================== Word 转 PDF ====================
def word_to_pdf(files, out_dir="", report=None, should_cancel=None, log=None):
    """将 Word 文档批量导出为 PDF（接受修订、删除批注，但不修改原文件）。

    需要本机安装 Microsoft Word。out_dir 为空时输出到 源目录+"_PDF"。
    返回成功数量。
    """
    _ensure_pywin32()
    try:
        import pythoncom  # noqa: F401
        import win32com.client
    except ImportError as e:
        raise RuntimeError(f"pywin32 组件加载失败: {e}")

    total = len(files)
    if total == 0:
        return 0

    word = None
    try:
        try:
            word = win32com.client.DispatchEx("Word.Application")
        except Exception as e:
            raise RuntimeError(
                f"无法启动 Microsoft Word（{e}）。请确认本机已安装 Word。"
            )
        word.Visible = False
        word.DisplayAlerts = 0

        ok = 0
        for idx, src in enumerate(files):
            if should_cancel and should_cancel():
                raise OperationCancelled()
            if report:
                report(idx / total, f"({idx + 1}/{total}) {os.path.basename(src)}")

            out = compute_output(src, None, out_dir, dir_suffix="_PDF", ext=".pdf")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            try:
                doc = word.Documents.Open(
                    os.path.abspath(src),
                    ConfirmConversions=False,
                    ReadOnly=False,
                    AddToRecentFiles=False,
                    Visible=False,
                )
                try:
                    # 接受修订、删除批注（仅内存中处理，不保存回原文件）
                    try:
                        doc.AcceptAllRevisions()
                    except Exception:
                        pass
                    for i in range(doc.Comments.Count, 0, -1):
                        doc.Comments(i).Delete()
                    doc.ExportAsFixedFormat(
                        OutputFileName=os.path.abspath(out),
                        ExportFormat=17,  # wdExportFormatPDF
                        OpenAfterExport=False,
                        OptimizeFor=0,
                        Range=0,
                        Item=0,  # 仅文档内容，不带修订标记
                        CreateBookmarks=0,
                    )
                finally:
                    doc.Close(SaveChanges=False)
                ok += 1
                if log:
                    log(f"✓ {src} → {out}")
            except OperationCancelled:
                raise
            except Exception as e:
                if log:
                    log(f"✗ 转换失败 {os.path.basename(src)}: {e}")
        return ok
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass


# ==================== PDF 权限限制 ====================
def set_pdf_permissions(files, out_dir="", password="", allow_print=False,
                        allow_copy=False, allow_modify=False,
                        allow_annotate=False, report=None,
                        should_cancel=None, log=None):
    """为 PDF 设置权限限制，打开始终无需密码。

    未勾选（False）的操作将被禁止：
    - allow_print: 打印（含高质量打印）
    - allow_copy: 复制文字/图片
    - allow_modify: 修改文档（含页面重组）
    - allow_annotate: 批注与填写表单
    无障碍读屏（辅助提取）始终保持可用。
    """
    flag = int(UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS)
    if allow_print:
        flag |= int(UserAccessPermissions.PRINT
                    | UserAccessPermissions.PRINT_TO_REPRESENTATION)
    if allow_copy:
        flag |= int(UserAccessPermissions.EXTRACT)
    if allow_modify:
        flag |= int(UserAccessPermissions.MODIFY
                    | UserAccessPermissions.ASSEMBLE_DOC)
    if allow_annotate:
        flag |= int(UserAccessPermissions.ADD_OR_MODIFY
                    | UserAccessPermissions.FILL_FORM_FIELDS)

    total = len(files)
    ok = 0
    for idx, src in enumerate(files):
        if should_cancel and should_cancel():
            raise OperationCancelled()
        if report:
            report(idx / total, f"({idx + 1}/{total}) {os.path.basename(src)}")
        out = compute_output(src, None, out_dir)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            reader = PdfReader(src)
            if reader.is_encrypted:
                if log:
                    log(f"✗ 已加密，跳过: {os.path.basename(src)}")
                continue
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.encrypt(
                user_password="",
                owner_password=password or "37259F97D4BC8CC4412B1E484E0A4F96",
                permissions_flag=flag,
            )
            with open(out, "wb") as f:
                writer.write(f)
            ok += 1
            if log:
                log(f"✓ {src} → {out}")
        except OperationCancelled:
            raise
        except Exception as e:
            if log:
                log(f"✗ 处理失败 {os.path.basename(src)}: {e}")
    return ok


# ==================== PDF 文字水印（矢量平铺） ====================
def _draw_watermark_pdf(text, font, page_w, page_h, rows, cols, font_size,
                        opacity, angle):
    """生成单页水印 PDF（内存中），画布使用页面实际尺寸"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_w, page_h))
    pdfmetrics.registerFont(TTFont("MSYH", font, subfontIndex=0))
    can.setFont("MSYH", font_size)
    can.setFillColorRGB(0, 0, 0)
    can.setFillAlpha(opacity)
    for row in range(rows):
        for col in range(cols):
            x = col * (page_w / cols) + (page_w / cols) / 2
            y = row * (page_h / rows) + (page_h / rows) / 2
            can.saveState()
            can.translate(x, y)
            can.rotate(angle)
            can.drawString(-can.stringWidth(text) / 2, 0, text)
            can.restoreState()
    can.save()
    packet.seek(0)
    return PdfReader(packet)


def add_text_watermark(files, out_dir="", text="杭州喜马拉雅", font=None,
                       rows=5, cols=3, font_size=18, opacity=0.2, angle=35,
                       report=None, should_cancel=None, log=None):
    """为 PDF 添加平铺文字水印（保留文字可选中等特性）"""
    font = font or font_path()
    total = len(files)
    ok = 0
    for idx, src in enumerate(files):
        if should_cancel and should_cancel():
            raise OperationCancelled()
        if report:
            report(idx / total, f"({idx + 1}/{total}) {os.path.basename(src)}")
        out = compute_output(src, None, out_dir)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            reader = PdfReader(src)
            writer = PdfWriter()
            for page in reader.pages:
                box = page.mediabox
                wm = _draw_watermark_pdf(text, font, float(box.width),
                                         float(box.height), rows, cols,
                                         font_size, opacity, angle)
                page.merge_page(wm.pages[0])
                writer.add_page(page)
            with open(out, "wb") as f:
                writer.write(f)
            ok += 1
            if log:
                log(f"✓ {src} → {out}")
        except OperationCancelled:
            raise
        except Exception as e:
            if log:
                log(f"✗ 处理失败 {os.path.basename(src)}: {e}")
    return ok


# ==================== PDF 转图片 + 水印（防提取编辑） ====================
def _tile_watermark_on_image(img, text, font, rows, cols, font_size,
                             opacity, angle):
    """在图片上平铺旋转文字水印（内存中完成）"""
    watermark = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark)
    padding = 4
    for i in range(rows):
        for j in range(cols):
            w, h = img.size
            text_img = Image.new(
                "RGBA", (font_size * len(text) + padding * 2,
                         font_size + padding * 2), (0, 0, 0, 0))
            td = ImageDraw.Draw(text_img)
            td.text((padding, padding), text, font=font,
                    fill=(0, 0, 0, int(255 * opacity)))
            rotated = text_img.rotate(angle, expand=True)
            x = int((j + 0.5) * w / cols - rotated.width / 2)
            y = int((i + 0.5) * h / rows - rotated.height / 2)
            watermark.paste(rotated, (x, y), rotated)
    return Image.alpha_composite(img.convert("RGBA"), watermark).convert("RGB")


def convert_to_image_pdf(files, out_dir="", text="杭州喜马拉雅", font=None,
                         rows=5, cols=2, font_size=36, opacity=0.3, angle=35,
                         zoom=1.5, quality=85,
                         report=None, should_cancel=None, log=None):
    """将 PDF 每页渲染为图片并平铺文字水印后重组（文字不可选中提取）"""
    font = font or font_path()
    truetype = ImageFont.truetype(font, font_size)
    total = len(files)
    ok = 0
    for idx, src in enumerate(files):
        if should_cancel and should_cancel():
            raise OperationCancelled()
        if report:
            report(idx / total, f"({idx + 1}/{total}) {os.path.basename(src)}")
        out = compute_output(src, None, out_dir)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            doc = fitz.open(src)
            output = fitz.open()
            page_total = doc.page_count
            for page_num in range(page_total):
                if should_cancel and should_cancel():
                    raise OperationCancelled()
                if report:
                    # 文件级进度 + 页级细分
                    report(
                        (idx + page_num / max(page_total, 1)) / total,
                        f"({idx + 1}/{total}) {os.path.basename(src)} "
                        f"第{page_num + 1}/{page_total}页",
                    )
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img = _tile_watermark_on_image(
                    img, text, truetype, rows, cols, font_size, opacity, angle
                )
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=min(quality, 100),
                         optimize=True)
                buf.seek(0)
                img_pdf = fitz.open("pdf", buf.getvalue())
                rect = img_pdf[0].rect
                new_page = output.new_page(width=rect.width, height=rect.height)
                new_page.insert_image(rect, stream=buf.getvalue())
            output.save(out, deflate=True, garbage=3)
            output.close()
            doc.close()
            ok += 1
            if log:
                log(f"✓ {src} → {out}")
        except OperationCancelled:
            raise
        except Exception as e:
            if log:
                log(f"✗ 处理失败 {os.path.basename(src)}: {e}")
    return ok


# ==================== 通用 GUI 工作线程 ====================
class PdfWorker(QThread):
    """在后台线程执行 pdf_tools 的批处理任务"""

    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, task, label, parent=None):
        super().__init__(parent)
        self.task = task          # 无参可调用（已用 lambda/functools.partial 绑定参数）
        self.label = label        # 任务名，用于完成提示
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        def report(frac, msg):
            self.progress.emit(min(int(frac * 100), 99))
            if msg:
                self.log.emit(msg)

        def should_cancel():
            return self._cancelled

        try:
            result = self.task(report=report, should_cancel=should_cancel,
                               log=self.log.emit)
            self.progress.emit(100)
            self.finished_signal.emit(True, f"{self.label}完成，共处理 {result} 个文件")
        except OperationCancelled:
            self.finished_signal.emit(False, "已取消")
        except Exception as e:
            self.finished_signal.emit(False, str(e))
