import os
import re
import json
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal

# Windows 下隐藏子进程的控制台窗口，避免黑框闪烁
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# NVENC 预设：p1 最快，p7 最慢。软编映射到 x264/x265 对应档位。
SPEED_KEYS = ("fastest", "fast", "balanced", "quality")
SPEED_LABELS = ("最快 (p1)", "较快 (p3)", "均衡 (p4)", "画质 (p6)")
NVENC_PRESETS = {
    "fastest": "p1",
    "fast": "p3",
    "balanced": "p4",
    "quality": "p6",
}
SOFT_PRESETS = {
    "fastest": "ultrafast",
    "fast": "veryfast",
    "balanced": "fast",
    "quality": "medium",
}
COPYABLE_VCODECS = {"h264", "hevc"}
# NVDEC 常见可硬解编码；其它格式走软解，避免 -hwaccel cuda 直接失败
HW_DECODE_CODECS = {
    "h264", "hevc", "av1", "vp9", "vp8",
    "mpeg1video", "mpeg2video", "mpeg4", "vc1", "mjpeg",
}


def normalize_speed(speed):
    if speed in NVENC_PRESETS:
        return speed
    return "balanced"


def speed_index(speed):
    try:
        return SPEED_KEYS.index(normalize_speed(speed))
    except ValueError:
        return 2


def speed_key_at(index):
    if 0 <= index < len(SPEED_KEYS):
        return SPEED_KEYS[index]
    return "balanced"


def resolve_encoder(codec, use_nvenc):
    """把界面上的 codec 名称解析成 ffmpeg 编码器名。"""
    name = (codec or "hevc_nvenc").lower()
    hevc = any(key in name for key in ("hevc", "h265", "265"))
    if use_nvenc:
        return "hevc_nvenc" if hevc else "h264_nvenc"
    return "libx265" if hevc else "libx264"


def hwaccel_prefix(use_nvenc, keep_on_gpu=False, vcodec=None):
    """NVENC 时对 NVDEC 能解的编码开启 CUDA 硬解。无 CPU 滤镜时可把帧留在 GPU 上。"""
    if not use_nvenc:
        return []
    if vcodec is not None and (vcodec or "").lower() not in HW_DECODE_CODECS:
        return []
    args = ["-hwaccel", "cuda"]
    if keep_on_gpu:
        args += ["-hwaccel_output_format", "cuda"]
    return args


def video_encode_args(codec, use_nvenc, speed="balanced", bitrate_k=None):
    encoder = resolve_encoder(codec, use_nvenc)
    speed = normalize_speed(speed)
    args = ["-c:v", encoder]
    if use_nvenc:
        args += ["-preset", NVENC_PRESETS[speed], "-tune", "hq", "-rc", "vbr"]
    else:
        args += ["-preset", SOFT_PRESETS[speed]]
    if bitrate_k:
        args += ["-b:v", f"{int(bitrate_k)}k"]
    return args


def audio_encode_args(audio_info=None, audio_bitrate=128, force_reencode=False):
    """源已经是 AAC 时直接 copy，否则转 AAC。无音轨则不加音频参数。"""
    codec = ""
    if audio_info:
        codec = (audio_info.get("codec") or "").lower()
    if not codec:
        return []
    if not force_reencode and codec == "aac":
        return ["-c:a", "copy"]
    return ["-c:a", "aac", "-b:a", f"{int(audio_bitrate)}k"]


def escape_filter_path(path):
    """转义后可放进 ffmpeg 滤镜图的路径（Windows 盘符冒号、反斜杠）。"""
    p = os.path.abspath(path).replace("\\", "/")
    p = p.replace("\\", "/").replace(":", "\\:").replace("'", r"\'")
    return f"'{p}'"


def profile_key(info):
    v = info.get("video") or {}
    a = info.get("audio") or {}
    return (
        (v.get("codec") or "").lower(),
        int(v.get("width") or 0),
        int(v.get("height") or 0),
        (a.get("codec") or "").lower(),
        int(a.get("sample_rate") or 0),
        int(a.get("channels") or 0),
    )


def pick_majority(infos):
    """选出可智能对齐的多数派编码参数。对不齐则返回 None。"""
    if len(infos) < 2:
        return None, 0
    keys = [profile_key(info) for _, info in infos]
    audio_present = [bool(key[3]) for key in keys]
    if len(set(audio_present)) > 1:
        return None, 0
    key, count = Counter(keys).most_common(1)[0]
    if count >= 2 and key[0] in COPYABLE_VCODECS:
        return key, count
    return None, 0


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
            "-show_entries",
            "format=duration,bit_rate:"
            "stream=codec_name,codec_type,profile,level,pix_fmt,"
            "width,height,r_frame_rate,sample_rate,channels,bit_rate",
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
        duration = float(fmt.get("duration", 0) or 0)
        return {
            "duration": duration,
            "bit_rate": int(fmt.get("bit_rate", 0) or 0),
            "video": {
                "codec": v_stream.get("codec_name", "") if v_stream else "",
                "profile": v_stream.get("profile", "") if v_stream else "",
                "width": int(v_stream.get("width", 0) or 0) if v_stream else 0,
                "height": int(v_stream.get("height", 0) or 0) if v_stream else 0,
                "fps": v_stream.get("r_frame_rate", "") if v_stream else "",
                "pix_fmt": v_stream.get("pix_fmt", "") if v_stream else "",
            },
            "audio": {
                "codec": a_stream.get("codec_name", "") if a_stream else "",
                "sample_rate": int(a_stream.get("sample_rate", 0) or 0) if a_stream else 0,
                "channels": int(a_stream.get("channels", 0) or 0) if a_stream else 0,
                "bit_rate": int(a_stream.get("bit_rate", 0) or 0) if a_stream else 0,
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

    def _write_concat_list(self, filepaths):
        list_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        for f in filepaths:
            safe = f.replace("\\", "/")
            list_file.write(f"file '{safe}'\n")
        list_file.close()
        return list_file.name

    def _concat_copy_cmd(self, filepaths, output):
        list_file = self._write_concat_list(filepaths)
        cmd = [
            self.ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy",
            "-movflags", "+faststart", output,
        ]
        return cmd, list_file

    def _transcode_to_profile_cmd(self, input_path, output_path, info, majority,
                                  use_nvenc, speed, audio_bitrate):
        maj_codec, maj_w, maj_h, maj_acodec, maj_ar, maj_ch = majority
        v = info["video"]
        a = info["audio"]
        need_v = (
            (v.get("codec") or "").lower() != maj_codec
            or int(v.get("width") or 0) != maj_w
            or int(v.get("height") or 0) != maj_h
        )
        need_a = (
            (a.get("codec") or "").lower() != maj_acodec
            or int(a.get("sample_rate") or 0) != maj_ar
            or int(a.get("channels") or 0) != maj_ch
        )
        keep_on_gpu = use_nvenc and need_v and not (
            int(v.get("width") or 0) != maj_w or int(v.get("height") or 0) != maj_h
        )
        cmd = [self.ffmpeg, "-y"]
        if need_v:
            cmd.extend(hwaccel_prefix(
                use_nvenc, keep_on_gpu=keep_on_gpu, vcodec=v.get("codec")))
        cmd.extend(["-i", input_path])
        if need_v and (int(v.get("width") or 0) != maj_w or int(v.get("height") or 0) != maj_h):
            cmd.extend([
                "-vf",
                f"scale={maj_w}:{maj_h}:force_original_aspect_ratio=decrease,"
                f"pad={maj_w}:{maj_h}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            ])
        if need_v:
            cmd.extend(video_encode_args(maj_codec, use_nvenc, speed))
        else:
            cmd.extend(["-c:v", "copy"])
        if maj_acodec:
            if need_a:
                cmd.extend(["-c:a", "aac", "-b:a", f"{int(audio_bitrate)}k"])
                if maj_ar:
                    cmd.extend(["-ar", str(maj_ar)])
                if maj_ch:
                    cmd.extend(["-ac", str(maj_ch)])
            else:
                cmd.extend(["-c:a", "copy"])
        cmd.append(output_path)
        return cmd

    def _concat_filter_cmd(self, filepaths, infos, output, codec, use_nvenc,
                           speed, audio_bitrate):
        """编码不一致时用 concat 滤镜重编码（concat demuxer 要求源流编码相同）。"""
        cmd = [self.ffmpeg, "-y"]
        for f, (_, info) in zip(filepaths, infos):
            cmd.extend(hwaccel_prefix(
                use_nvenc, keep_on_gpu=False, vcodec=info["video"].get("codec")))
            cmd.extend(["-i", f])
        n = len(filepaths)
        tw = max(info["video"]["width"] for _, info in infos) or 1920
        th = max(info["video"]["height"] for _, info in infos) or 1080
        has_audio = all((info["audio"].get("codec") or "") for _, info in infos)
        parts = []
        maps = []
        for i in range(n):
            parts.append(
                f"[{i}:v:0]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]"
            )
            maps.append(f"[v{i}]")
            if has_audio:
                maps.append(f"[{i}:a:0]")
        if has_audio:
            fc = ";".join(parts) + ";" + "".join(maps) + f"concat=n={n}:v=1:a=1[v][a]"
        else:
            fc = ";".join(parts) + ";" + "".join(maps) + f"concat=n={n}:v=1:a=0[v]"
        cmd.extend(["-filter_complex", fc, "-map", "[v]"])
        if has_audio:
            cmd.extend(["-map", "[a]"])
        cmd.extend(video_encode_args(codec, use_nvenc, speed))
        if has_audio:
            cmd.extend(["-c:a", "aac", "-b:a", f"{int(audio_bitrate)}k"])
        cmd.extend(["-movflags", "+faststart", output])
        return cmd

    def build_merge_plan(self, filepaths, output, infos, re_encode=False,
                         codec="hevc_nvenc", use_nvenc=True, audio_bitrate=128,
                         speed="balanced"):
        """返回 {steps, cleanup, total_duration}。steps 供 FFmpegWorker 顺序执行。"""
        total_duration = sum(info["duration"] for _, info in infos) if infos else 0
        cleanup = []

        if not re_encode:
            cmd, list_file = self._concat_copy_cmd(filepaths, output)
            cleanup.append(list_file)
            return {
                "steps": [{
                    "cmd": cmd,
                    "duration": total_duration,
                    "label": "无损合并",
                    "weight": max(total_duration, 0.1),
                }],
                "cleanup": cleanup,
                "total_duration": total_duration,
            }

        majority, count = pick_majority(infos)
        if majority:
            work_dir = tempfile.mkdtemp(prefix="mediakit_merge_")
            cleanup.append(work_dir)
            ext = os.path.splitext(output)[1] or ".mp4"
            concat_inputs = []
            steps = []
            for i, (path, info) in enumerate(infos):
                if profile_key(info) == majority:
                    concat_inputs.append(path)
                    continue
                part = os.path.join(work_dir, f"part_{i:03d}{ext}")
                cmd = self._transcode_to_profile_cmd(
                    path, part, info, majority, use_nvenc, speed, audio_bitrate)
                steps.append({
                    "cmd": cmd,
                    "duration": info["duration"],
                    "label": f"转码对齐 {os.path.basename(path)}",
                    "weight": max(info["duration"], 0.1),
                })
                concat_inputs.append(part)
            concat_cmd, list_file = self._concat_copy_cmd(concat_inputs, output)
            cleanup.append(list_file)
            steps.append({
                "cmd": concat_cmd,
                "duration": total_duration,
                "label": f"无损拼接（{count}/{len(infos)} 个文件已对齐，其余已转码）",
                "weight": max(1.0, total_duration * 0.02),
            })
            return {
                "steps": steps,
                "cleanup": cleanup,
                "total_duration": total_duration,
            }

        cmd = self._concat_filter_cmd(
            filepaths, infos, output, codec, use_nvenc, speed, audio_bitrate)
        return {
            "steps": [{
                "cmd": cmd,
                "duration": total_duration,
                "label": "重编码合并",
                "weight": max(total_duration, 0.1),
            }],
            "cleanup": cleanup,
            "total_duration": total_duration,
        }

    def build_compress_command(self, input_path, output, target_size_mb, duration,
                                codec="hevc_nvenc", use_nvenc=True, audio_bitrate=128,
                                output_format="mp4", audio_info=None, speed="balanced",
                                video_info=None):
        target_bytes = target_size_mb * 1024 * 1024
        audio_args = audio_encode_args(audio_info, audio_bitrate)
        copying_audio = audio_args == ["-c:a", "copy"]
        if copying_audio and audio_info and int(audio_info.get("bit_rate") or 0) > 0:
            audio_bps = int(audio_info["bit_rate"])
        else:
            audio_bps = audio_bitrate * 1024
        if not audio_args:
            audio_bps = 0
        total_bitrate = int(target_bytes * 8 / duration * 0.97)
        video_bitrate = max(total_bitrate - audio_bps, 100000)
        video_bitrate_k = video_bitrate // 1000
        maxrate_k = int(video_bitrate_k * 1.2)
        bufsize_k = video_bitrate_k * 2

        vcodec = (video_info or {}).get("codec")
        cmd = [self.ffmpeg, "-y"]
        cmd.extend(hwaccel_prefix(use_nvenc, keep_on_gpu=True, vcodec=vcodec))
        cmd.extend(["-i", input_path])
        cmd.extend(video_encode_args(codec, use_nvenc, speed))
        cmd.extend([
            "-b:v", f"{video_bitrate_k}k",
            "-maxrate", f"{maxrate_k}k",
            "-bufsize", f"{bufsize_k}k",
        ])
        cmd.extend(audio_args)
        cmd.extend(["-movflags", "+faststart", output])
        return cmd, {
            "video_bitrate": video_bitrate_k,
            "total_bitrate": total_bitrate // 1000,
            "estimated_size_mb": target_size_mb,
            "audio_copy": copying_audio,
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
    """在后台线程运行 FFmpeg，支持单命令或多步骤任务。"""

    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, cmd=None, duration=0, temp_file=None, steps=None, cleanup=None):
        super().__init__()
        if steps:
            self.steps = steps
        else:
            self.steps = [{
                "cmd": cmd or [],
                "duration": duration,
                "label": "",
                "weight": max(duration or 0, 0.1),
            }]
        self.cleanup = list(cleanup or [])
        if temp_file:
            self.cleanup.append(temp_file)
        self._cancelled = False
        self._process = None

    def cancel(self):
        self._cancelled = True
        if self._process is not None:
            try:
                self._process.kill()
            except Exception:
                pass

    def run(self):
        try:
            total_weight = sum(max(step.get("weight") or 0, 0.1) for step in self.steps)
            done_weight = 0.0
            n = len(self.steps)
            for i, step in enumerate(self.steps):
                if self._cancelled:
                    self.finished_signal.emit(False, "已取消")
                    return
                label = step.get("label") or ""
                if n > 1:
                    self.log.emit(f"[{i + 1}/{n}] {label}".strip())
                ok, msg = self._run_one(step, done_weight, total_weight)
                if self._cancelled:
                    self.finished_signal.emit(False, "已取消")
                    return
                if not ok:
                    self.finished_signal.emit(False, msg)
                    return
                done_weight += max(step.get("weight") or 0, 0.1)
            self.progress.emit(100)
            self.finished_signal.emit(True, "完成")
        except Exception as e:
            self.finished_signal.emit(False, str(e))
        finally:
            self._cleanup()

    def _run_one(self, step, done_weight, total_weight):
        cmd = step.get("cmd") or []
        duration = float(step.get("duration") or 0)
        weight = max(step.get("weight") or 0, 0.1)
        self.log.emit("命令: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self._process = process
        try:
            for line in process.stderr:
                if self._cancelled:
                    process.kill()
                    return False, "已取消"
                line = line.strip()
                if line:
                    self.log.emit(line)
                if "time=" in line:
                    m = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", line)
                    if m and duration > 0 and total_weight > 0:
                        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                        frac = min(t / duration, 1.0)
                        pct = min(int((done_weight + frac * weight) / total_weight * 100), 99)
                        self.progress.emit(pct)
            process.wait()
        finally:
            self._process = None
        if process.returncode == 0:
            return True, "完成"
        return False, f"FFmpeg 返回码: {process.returncode}"

    def _cleanup(self):
        for path in self.cleanup:
            try:
                if not path:
                    continue
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass
