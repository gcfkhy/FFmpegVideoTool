import json
import os
import shutil
import sys


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
        ffmpeg, ffprobe = self._auto_detect()
        return {
            "ffmpeg_path": ffmpeg,
            "ffprobe_path": ffprobe,
            "default_codec": "hevc_nvenc",
            "default_audio_bitrate": 128,
            "use_nvenc": True,
            "last_output_dir": "",
        }

    @staticmethod
    def _auto_detect():
        for name in ("ffmpeg", "ffmpeg.exe"):
            p = shutil.which(name)
            if p:
                d = os.path.dirname(p)
                ffprobe = os.path.join(d, "ffprobe.exe")
                if os.path.exists(ffprobe):
                    return p, ffprobe
                return p, ""
        hardcoded = r"D:\E\word转pdf\ffmpeg\ffmpeg.exe"
        if os.path.exists(hardcoded):
            return hardcoded, r"D:\E\word转pdf\ffmpeg\ffprobe.exe"
        return "", ""

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
