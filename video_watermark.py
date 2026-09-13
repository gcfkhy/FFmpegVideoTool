# -*- coding: utf-8 -*-
"""视频文字水印核心逻辑。

移植自 D:\\word转pdf 的 VideoWatermark.py / VideoWatermarkNewFile.py /
VideoZIP.py 三个重复实现，保留共同行为并优化：
- 水印按随机时间出现（每段 5 秒，从左向右飘过），位置纵向随机
- 通过写入 comment=LinLong 元数据标记已处理文件，避免重复加水印
- 输出方式可选：替换原文件 或 另存新文件
- 去除 eval()、numpy 依赖；drawtext 参数做转义处理
- 编码器复用主程序设置（NVENC 硬件加速 / 软编）
"""
import os
import re
import json
import random
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal

from ffmpeg_core import NO_WINDOW  # 复用隐藏控制台窗口常量

MARKER = "LinLong"  # 已加水印的元数据标记
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".ts", ".wmv")


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


def _ff_escape_path(path):
    """转义 drawtext fontfile 的 Windows 路径（盘符冒号需转义）"""
    p = path.replace("\\", "/").replace(":", "\\:")
    return f"'{p}'"


def _ff_escape_text(text):
    """转义 drawtext 文本中的特殊字符"""
    for ch in ("\\", "'", ":", "%"):
        text = text.replace(ch, "\\" + ch)
    return text


def probe_video(ffprobe, path):
    """获取视频分辨率/帧率/时长/comment 标记"""
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate:format=duration:format_tags=comment",
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
        stream = (info.get("streams") or [None])[0]
        if not stream:
            return None
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        if width <= 0 or height <= 0:
            return None
        # 帧率形如 "30000/1001"
        fps = 0.0
        rate = stream.get("r_frame_rate", "0/1")
        try:
            num, _, den = rate.partition("/")
            fps = float(num) / float(den or 1)
        except Exception:
            pass
        try:
            duration = float(info.get("format", {}).get("duration", 0))
        except (TypeError, ValueError):
            duration = 0.0
        comment = info.get("format", {}).get("tags", {}).get("comment", "")
        return {
            "width": width, "height": height,
            "fps": fps, "duration": duration, "comment": comment.strip(),
        }
    except Exception:
        return None


def is_marked(probe):
    """是否已加水印（按元数据标记判断）"""
    return bool(probe) and probe.get("comment") == MARKER


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
        # 末段由 enable=between 自然截断，短视频也保证 t=0 处出现一次
        if random.random() < 0.7:
            y = random.randint(int(0.40 * height), int(0.59 * height))
        else:
            y = random.randint(0, int(0.40 * height))
        positions.append((round(current, 2), y))
        current += interval
    return positions


def build_command(ffmpeg, input_path, output_path, font, probe,
                  text="示例水印文字", color="#FF0000", fontsize=40,
                  alpha=0.3, frequency_factor=7, video_bitrate_k=2000,
                  audio_bitrate_k=192, codec="hevc_nvenc", use_nvenc=True,
                  marked=True):
    """构建加水印的 ffmpeg 命令，返回 (cmd, duration)"""
    width, height = probe["width"], probe["height"]
    new_w, new_h = _target_size(width, height)
    filters = []
    if (new_w, new_h) != (width, height):
        filters.append(f"scale={new_w}:{new_h}")
    for start, y in generate_positions(probe["duration"], frequency_factor, new_h):
        filters.append(
            f"drawtext=fontfile={_ff_escape_path(font)}:"
            f"text='{_ff_escape_text(text)}':"
            f"fontcolor={color}:fontsize={fontsize}:alpha={alpha}:"
            f"x='if(between(t,{start},{start + 5}),(w-text_w)*(t-{start})/5,NAN)':"
            f"y={y}"
        )
    cmd = [ffmpeg, "-y", "-i", input_path]
    if marked:
        cmd.extend(["-metadata", f"comment={MARKER}"])
    if filters:
        cmd.extend(["-vf", ",".join(filters)])
    cmd.extend(["-c:v", codec, "-b:v", f"{video_bitrate_k}k"])
    if use_nvenc:
        cmd.extend(["-preset", "p6", "-tune", "hq", "-rc", "vbr"])
    else:
        cmd.extend(["-preset", "medium"])
    cmd.extend(["-c:a", "aac", "-b:a", f"{audio_bitrate_k}k"])
    cmd.append(output_path)
    return cmd, probe["duration"]


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
        """jobs: [(input_path, temp_path, replace, cmd, duration), ...]"""
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

    def _run_one(self, idx, input_path, temp_path, replace, cmd, duration):
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

    def run(self):
        done = 0
        for idx, (input_path, temp_path, replace, cmd,
                  duration) in enumerate(self.jobs):
            if self._cancelled:
                break
            try:
                if self._run_one(idx, input_path, temp_path, replace, cmd,
                                 duration):
                    done += 1
            except Exception as e:
                self.log.emit(f"✗ 异常: {e}")
        if self._cancelled:
            self.finished_signal.emit(False, "已取消")
        else:
            self.progress.emit(100)
            self.finished_signal.emit(
                True, f"完成，成功处理 {done}/{len(self.jobs)} 个文件")
