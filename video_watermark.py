# -*- coding: utf-8 -*-
"""视频文字水印核心逻辑。

移植自 D:\\word转pdf 的 VideoWatermark.py / VideoWatermarkNewFile.py /
VideoZIP.py 三个重复实现，保留共同行为并优化：
- 水印按随机时间出现（每段 5 秒，从左向右飘过），位置纵向随机
- 通过写入 comment=MediaKit 元数据标记已处理文件，避免重复加水印
- 输出方式可选：替换原文件 或 另存新文件
- 水印烧录改用 ASS（一条 subtitles 滤镜），避免上百条 drawtext
- 编码器复用主程序设置（NVENC 硬件加速 / 软编）
"""
import os
import re
import json
import random
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import QThread, pyqtSignal

from ffmpeg_core import (
    NO_WINDOW,
    audio_encode_args,
    escape_filter_path,
    hwaccel_prefix,
    video_encode_args,
)

MARKER = "MediaKit"  # 已加水印的元数据标记
LEGACY_MARKERS = {"LinLong"}  # 兼容旧版本写入的标记
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".ts", ".wmv")
ASS_FONT_NAME = "Microsoft YaHei"
WATERMARK_HOLD = 5.0


def collect_videos(paths):
    """收集视频文件，目录递归扫描，去重保序"""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                for name in sorted(names):
                    if name.lower().endswith(VIDEO_EXTS):
                        files.append(os.path.join(root, name))
        elif os.path.isfile(p) and p.lower().endswith(VIDEO_EXTS):
            files.append(p)
    seen = set()
    unique = []
    for f in files:
        key = os.path.normcase(os.path.abspath(f))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def probe_video(ffprobe, path):
    """获取视频分辨率/帧率/时长/comment 标记/音频编码"""
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate,"
        "sample_rate,channels:format=duration:format_tags=comment",
        "-of", "json", path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=NO_WINDOW,
        )
        if result.returncode != 0:
            return None
        info = json.loads(result.stdout)
        streams = info.get("streams") or []
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if not v_stream:
            return None
        width = int(v_stream.get("width", 0) or 0)
        height = int(v_stream.get("height", 0) or 0)
        if width <= 0 or height <= 0:
            return None
        fps = 0.0
        rate = v_stream.get("r_frame_rate", "0/1")
        try:
            num, _, den = rate.partition("/")
            fps = float(num) / float(den or 1)
        except Exception:
            pass
        try:
            duration = float(info.get("format", {}).get("duration", 0) or 0)
        except (TypeError, ValueError):
            duration = 0.0
        tags = info.get("format", {}).get("tags") or {}
        comment = tags.get("comment", "")
        return {
            "width": width, "height": height,
            "codec": v_stream.get("codec_name", "") or "",
            "fps": fps, "duration": duration, "comment": comment.strip(),
            "audio": {
                "codec": a_stream.get("codec_name", "") if a_stream else "",
                "sample_rate": int(a_stream.get("sample_rate", 0) or 0) if a_stream else 0,
                "channels": int(a_stream.get("channels", 0) or 0) if a_stream else 0,
            },
        }
    except Exception:
        return None


def probe_videos(ffprobe, files, max_workers=8):
    """并行探测，返回与 files 等长的 probe 列表。"""
    if not files:
        return []
    results = [None] * len(files)
    workers = max(1, min(max_workers, len(files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(probe_video, ffprobe, f): i for i, f in enumerate(files)}
        for fut in as_completed(futs):
            results[futs[fut]] = fut.result()
    return results


def is_marked(probe):
    """是否已加水印（按元数据标记判断，兼容旧版本标记）"""
    return bool(probe) and probe.get("comment") in ({MARKER} | LEGACY_MARKERS)


def _target_size(width, height, max_w=1920, max_h=1080):
    """限制最大分辨率，保持宽高比"""
    if width <= max_w and height <= max_h:
        return width, height
    ratio = min(max_w / width, max_h / height)
    return int(width * ratio), int(height * ratio)


def generate_positions(duration, frequency_factor=7, height=1080):
    """生成水印出现时间段与纵向位置（全程覆盖，间隔随频率因子缩短）"""
    positions = []
    interval = max(30, min(180, 180 / max(frequency_factor, 1)))
    current = 0.0
    while current < duration:
        # 末段由结束时间截断，短视频也保证 t=0 处出现一次
        if random.random() < 0.7:
            y = random.randint(int(0.40 * height), int(0.59 * height))
        else:
            y = random.randint(0, int(0.40 * height))
        positions.append((round(current, 2), y))
        current += interval
    return positions


def _ass_time(seconds):
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text):
    return (text.replace("\\", r"\\")
                .replace("{", r"\{")
                .replace("}", r"\}")
                .replace("\n", r"\N"))


def _css_to_ass_color(hex_color, alpha):
    """#RRGGBB + 不透明度 0-1 → ASS &HAABBGGRR（AA=00 不透明）。"""
    color = (hex_color or "#FF0000").lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    if len(color) != 6:
        color = "FF0000"
    try:
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
    except ValueError:
        r, g, b = 255, 0, 0
    a = int(round((1.0 - max(0.0, min(1.0, float(alpha)))) * 255))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def _text_width_px(font_path, text, fontsize):
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(font_path, fontsize)
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return max(bbox[2] - bbox[0], 1)
        return max(int(fontsize * len(text)), 1)
    except Exception:
        width = 0
        for ch in text:
            width += fontsize if ord(ch) > 127 else int(fontsize * 0.55)
        return max(width, 1)


def build_ass(width, height, duration, font_path, text, color, fontsize, alpha,
              frequency_factor):
    """生成与旧 drawtext 行为一致的 ASS 字幕文本。"""
    positions = generate_positions(duration, frequency_factor, height)
    primary = _css_to_ass_color(color, alpha)
    text_w = _text_width_px(font_path, text, fontsize)
    end_x = max(0, int(width - text_w))
    escaped = _ass_escape(text)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {int(width)}",
        f"PlayResY: {int(height)}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: WM,{ASS_FONT_NAME},{int(fontsize)},{primary},"
        "&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for start, y in positions:
        end = min(start + WATERMARK_HOLD, duration if duration > 0 else start + WATERMARK_HOLD)
        if end <= start:
            continue
        y = max(0, int(y))
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},WM,,0,0,0,,"
            f"{{\\move(0,{y},{end_x},{y})}}{escaped}"
        )
    return "\n".join(lines) + "\n"


def write_ass_file(content):
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ass", delete=False, encoding="utf-8"
    )
    handle.write(content)
    handle.close()
    return handle.name


def build_command(ffmpeg, input_path, output_path, font, probe,
                  text="示例水印文字", color="#FF0000", fontsize=40,
                  alpha=0.3, frequency_factor=7, video_bitrate_k=2000,
                  audio_bitrate_k=192, codec="hevc_nvenc", use_nvenc=True,
                  marked=True, speed="balanced"):
    """构建加水印的 ffmpeg 命令，返回 (cmd, duration, extra_temps)"""
    width, height = probe["width"], probe["height"]
    new_w, new_h = _target_size(width, height)
    ass_text = build_ass(
        new_w, new_h, probe["duration"], font, text, color, fontsize,
        alpha, frequency_factor,
    )
    ass_path = write_ass_file(ass_text)
    fontsdir = os.path.dirname(os.path.abspath(font)) if font else ""
    filters = []
    if (new_w, new_h) != (width, height):
        filters.append(f"scale={new_w}:{new_h}")
    sub = f"subtitles=f={escape_filter_path(ass_path)}"
    if fontsdir:
        sub += f":fontsdir={escape_filter_path(fontsdir)}"
    filters.append(sub)

    cmd = [ffmpeg, "-y"]
    cmd.extend(hwaccel_prefix(
        use_nvenc, keep_on_gpu=False, vcodec=probe.get("codec")))
    cmd.extend(["-i", input_path])
    if marked:
        cmd.extend(["-metadata", f"comment={MARKER}"])
    if filters:
        cmd.extend(["-vf", ",".join(filters)])
    cmd.extend(video_encode_args(
        codec, use_nvenc, speed, bitrate_k=video_bitrate_k))
    cmd.extend(audio_encode_args(probe.get("audio"), audio_bitrate_k))
    cmd.append(output_path)
    return cmd, probe["duration"], [ass_path]


def suggest_output(input_path, as_new_file):
    """计算输出路径：替换原文件先用同扩展名临时文件，另存则加 _watermarked 后缀"""
    root, ext = os.path.splitext(input_path)
    if as_new_file:
        return f"{root}_watermarked{ext}"
    return f"{root}.watermarking{ext}"


class VideoWatermarkWorker(QThread):
    """后台批量执行视频加水印"""

    progress = pyqtSignal(int)          # 总进度 0-100
    file_progress = pyqtSignal(int)     # 当前文件进度 0-100
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, jobs, parent=None):
        """jobs: [(input_path, temp_path, replace, cmd, duration, extra_temps), ...]"""
        super().__init__(parent)
        self.jobs = jobs
        self._cancelled = False
        self._process = None

    def cancel(self):
        self._cancelled = True
        if self._process is not None:
            try:
                self._process.kill()
            except Exception:
                pass

    def _run_one(self, idx, input_path, temp_path, replace, cmd, duration, extra_temps):
        total = len(self.jobs)
        self.log.emit(f"({idx + 1}/{total}) {input_path}")
        self.log.emit("命令: " + " ".join(
            f'"{c}"' if " " in c else c for c in cmd))
        process = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=NO_WINDOW,
        )
        self._process = process
        try:
            for line in process.stderr:
                if self._cancelled:
                    break
                line = line.strip()
                if line:
                    self.log.emit(line)
                if "time=" in line and duration > 0:
                    m = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", line)
                    if m:
                        t = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                             + float(m.group(3)))
                        file_pct = min(int(t / duration * 100), 100)
                        self.file_progress.emit(file_pct)
                        overall = (idx + file_pct / 100) / total
                        self.progress.emit(min(int(overall * 100), 99))
            process.wait()
        finally:
            self._process = None
            self._cleanup_temps(extra_temps)
        if self._cancelled:
            self._cleanup_temp(temp_path, input_path)
            return False
        if process.returncode != 0:
            self._cleanup_temp(temp_path, input_path)
            self.log.emit(f"✗ 失败（返回码 {process.returncode}）: "
                          f"{os.path.basename(input_path)}")
            return False
        if replace:
            os.replace(temp_path, input_path)
        return True

    @staticmethod
    def _cleanup_temp(temp_path, input_path):
        try:
            if os.path.abspath(temp_path) != os.path.abspath(input_path) \
                    and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass

    @staticmethod
    def _cleanup_temps(paths):
        for path in paths or []:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def run(self):
        done = 0
        for idx, job in enumerate(self.jobs):
            if self._cancelled:
                break
            input_path, temp_path, replace, cmd, duration = job[:5]
            extra_temps = job[5] if len(job) > 5 else []
            try:
                if self._run_one(idx, input_path, temp_path, replace, cmd,
                                 duration, extra_temps):
                    done += 1
            except Exception as e:
                self.log.emit(f"✗ 异常: {e}")
                self._cleanup_temps(extra_temps)
        if self._cancelled:
            self.finished_signal.emit(False, "已取消")
        else:
            self.progress.emit(100)
            self.finished_signal.emit(
                True, f"完成，成功处理 {done}/{len(self.jobs)} 个文件")
