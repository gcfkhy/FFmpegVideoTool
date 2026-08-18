import os
import re
import json
import subprocess
import tempfile
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal

# Windows 下隐藏子进程的控制台窗口，避免黑框闪烁
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class FileSorter:
    """按文件名中的时间戳排序，回退到文件创建时间"""

    TIMESTAMP_PATTERNS = [
        r"(\d{4})(\d{2})(\d{2})[-_]?(\d{2})(\d{2})(\d{2})",
        r"(\d{4})[-_](\d{2})[-_](\d{2})[-_]?(\d{2})[-_](\d{2})[-_](\d{2})",
        r"(\d{4})(\d{2})(\d{2})",
        r"(\d{4})[-_](\d{2})[-_](\d{2})",
    ]

    @classmethod
    def extract_timestamp(cls, filepath):
        name = os.path.basename(filepath)
        for pattern in cls.TIMESTAMP_PATTERNS:
            m = re.search(pattern, name)
            if m:
                groups = m.groups()
                try:
                    if len(groups) >= 6:
                        return datetime(
                            int(groups[0]), int(groups[1]), int(groups[2]),
                            int(groups[3]), int(groups[4]), int(groups[5]),
                        )
                    elif len(groups) >= 3:
                        return datetime(
                            int(groups[0]), int(groups[1]), int(groups[2])
                        )
                except ValueError:
                    continue
        try:
            ts = os.path.getctime(filepath)
            return datetime.fromtimestamp(ts)
        except Exception:
            return datetime.min

    @classmethod
    def sort_files(cls, filepaths):
        return sorted(filepaths, key=cls.extract_timestamp)


class FFmpegWrapper:
    """封装 FFmpeg/FFprobe 调用"""

    def __init__(self, ffmpeg_path, ffprobe_path):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path

    def probe(self, filepath):
        if not self.ffprobe or not os.path.exists(self.ffprobe):
            return None
        cmd = [
            self.ffprobe, "-v", "error",
            "-show_entries", "format=duration,bit_rate:stream=codec_name,codec_type,profile,level,pix_fmt,width,height,r_frame_rate,sample_rate,channels",
            "-of", "json", filepath,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                creationflags=NO_WINDOW,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    @staticmethod
    def parse_probe(info):
        if not info:
            return None
        fmt = info.get("format", {})
        streams = info.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = float(fmt.get("duration", 0))
        return {
            "duration": duration,
            "bit_rate": int(fmt.get("bit_rate", 0)),
            "video": {
                "codec": v_stream.get("codec_name", "") if v_stream else "",
                "profile": v_stream.get("profile", "") if v_stream else "",
                "width": int(v_stream.get("width", 0)) if v_stream else 0,
                "height": int(v_stream.get("height", 0)) if v_stream else 0,
                "fps": v_stream.get("r_frame_rate", "") if v_stream else "",
                "pix_fmt": v_stream.get("pix_fmt", "") if v_stream else "",
            },
            "audio": {
                "codec": a_stream.get("codec_name", "") if a_stream else "",
                "sample_rate": int(a_stream.get("sample_rate", 0)) if a_stream else 0,
                "channels": int(a_stream.get("channels", 0)) if a_stream else 0,
            },
        }

    def check_compatibility(self, filepaths):
        infos = []
        for f in filepaths:
            info = self.parse_probe(self.probe(f))
            if info:
                infos.append((f, info))
            else:
                return False, f"无法探测文件: {os.path.basename(f)}", []
        if len(infos) < 2:
            return True, "", infos
        first = infos[0][1]
        for filepath, info in infos[1:]:
            if (info["video"]["codec"] != first["video"]["codec"] or
                info["video"]["width"] != first["video"]["width"] or
                info["video"]["height"] != first["video"]["height"] or
                info["audio"]["codec"] != first["audio"]["codec"] or
                info["audio"]["sample_rate"] != first["audio"]["sample_rate"]):
                return False, "文件编码参数不一致，需要重编码合并", infos
        return True, "所有文件编码一致，可无损合并", infos

    def build_merge_command(self, filepaths, output, re_encode=False, codec="hevc_nvenc", use_nvenc=True, audio_bitrate=128):
        list_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        for f in filepaths:
            safe = f.replace("\\", "/")
            list_file.write(f"file '{safe}'\n")
        list_file.close()

        cmd = [self.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_file.name]
        if re_encode:
            v_encoder = codec if use_nvenc else codec.replace("_nvenc", "")
            cmd.extend(["-c:v", v_encoder, "-preset", "p6"])
            if use_nvenc:
                cmd.extend(["-tune", "hq", "-rc", "vbr"])
            cmd.extend(["-c:a", "aac", "-b:a", f"{audio_bitrate}k"])
        else:
            cmd.extend(["-c", "copy"])
        cmd.extend(["-movflags", "+faststart", output])
        return cmd, list_file.name

    def build_compress_command(self, input_path, output, target_size_mb, duration,
                                codec="hevc_nvenc", use_nvenc=True, audio_bitrate=128, output_format="mp4"):
        target_bytes = target_size_mb * 1024 * 1024
        total_bitrate = int(target_bytes * 8 / duration * 0.97)
        video_bitrate = max(total_bitrate - audio_bitrate * 1024, 100000)
        video_bitrate_k = video_bitrate // 1000
        maxrate_k = int(video_bitrate_k * 1.2)
        bufsize_k = video_bitrate_k * 2

        v_encoder = codec if use_nvenc else codec.replace("_nvenc", "")
        cmd = [self.ffmpeg, "-y", "-i", input_path]
        cmd.extend(["-c:v", v_encoder, "-preset", "p6"])
        if use_nvenc:
            cmd.extend(["-tune", "hq", "-rc", "vbr"])
        cmd.extend([
            "-b:v", f"{video_bitrate_k}k",
            "-maxrate", f"{maxrate_k}k",
            "-bufsize", f"{bufsize_k}k",
        ])
        cmd.extend(["-c:a", "aac", "-b:a", f"{audio_bitrate}k"])
        cmd.extend(["-movflags", "+faststart", output])
        return cmd, {
            "video_bitrate": video_bitrate_k,
            "total_bitrate": total_bitrate // 1000,
            "estimated_size_mb": target_size_mb,
        }

    def check_nvenc(self):
        if not self.ffmpeg or not os.path.exists(self.ffmpeg):
            return False
        try:
            result = subprocess.run(
                [self.ffmpeg, "-encoders"],
                capture_output=True, text=True, timeout=10,
                creationflags=NO_WINDOW,
            )
            return "hevc_nvenc" in result.stdout
        except Exception:
            return False

    @staticmethod
    def format_duration(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @staticmethod
    def format_size(size_bytes):
        if size_bytes >= 1024 ** 3:
            return f"{size_bytes / 1024**3:.2f} GB"
        return f"{size_bytes / 1024**2:.1f} MB"


class FFmpegWorker(QThread):
    """在后台线程运行 FFmpeg"""

    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, cmd, duration, temp_file=None):
        super().__init__()
        self.cmd = cmd
        self.duration = duration
        self.temp_file = temp_file
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.log.emit("命令: " + " ".join(f'"{c}"' if " " in c else c for c in self.cmd))
            process = subprocess.Popen(
                self.cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in process.stderr:
                if self._cancelled:
                    process.kill()
                    self.finished_signal.emit(False, "已取消")
                    return
                line = line.strip()
                if line:
                    self.log.emit(line)
                if "time=" in line:
                    m = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", line)
                    if m and self.duration > 0:
                        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                        pct = min(int(t / self.duration * 100), 99)
                        self.progress.emit(pct)
            process.wait()
            if process.returncode == 0:
                self.progress.emit(100)
                self.finished_signal.emit(True, "完成")
            else:
                self.finished_signal.emit(False, f"FFmpeg 返回码: {process.returncode}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))
        finally:
            if self.temp_file and os.path.exists(self.temp_file):
                try:
                    os.unlink(self.temp_file)
                except Exception:
                    pass
