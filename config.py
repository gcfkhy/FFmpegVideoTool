import json
import os
import sys


def _exe_dir():
    """exe 所在目录；开发模式下为源码目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _bundled_ffmpeg(name):
    """定位随包分发的 ffmpeg 可执行文件。

    优先级：exe 同目录 ffmpeg_bin（便于用户替换升级）> PyInstaller 单文件解包目录（exe 内置）。
    """
    p = os.path.join(_exe_dir(), "ffmpeg_bin", name)
    if os.path.exists(p):
        return p
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = os.path.join(meipass, "ffmpeg_bin", name)
        if os.path.exists(p):
            return p
    return ""


class Config:
    """管理应用配置，支持便携模式和安装模式"""

    def __init__(self):
        self._appdata_dir = os.path.join(
            os.environ.get("APPDATA", ""), "FFmpegVideoTool"
        )
        self.data = self._load()

    def _is_portable(self):
        exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.exists(os.path.join(exe_dir, "portable.flag"))

    def _config_path(self):
        if self._is_portable():
            exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            return os.path.join(exe_dir, "config.json")
        os.makedirs(self._appdata_dir, exist_ok=True)
        return os.path.join(self._appdata_dir, "config.json")

    def _load(self):
        path = self._config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self._defaults()

    def save(self):
        path = self._config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _defaults(self):
        return {
            "default_codec": "hevc_nvenc",
            "default_audio_bitrate": 128,
            "use_nvenc": True,
            "last_output_dir": "",
            "theme": "light",
        }

    def get(self, key, default=None):
        if key in ("ffmpeg_path", "ffprobe_path"):
            # 内置的 ffmpeg 优先，用户无需任何配置
            name = "ffmpeg.exe" if key == "ffmpeg_path" else "ffprobe.exe"
            bundled = _bundled_ffmpeg(name)
            if bundled:
                return bundled
            # 未打包内置时回退到已配置/检测到的路径
            return self.data.get(key, "")
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
