# -*- coding: utf-8 -*-
"""命令拼装与智能合并启发式的轻量测试，不启动 GUI。"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ffmpeg_core import (
    FFmpegWrapper, SPEED_KEYS, audio_encode_args, escape_filter_path,
    hwaccel_prefix, pick_majority, profile_key, resolve_encoder,
    speed_index, speed_key_at, video_encode_args,
)
from video_watermark import (
    _css_to_ass_color, build_ass, build_command, generate_positions,
)


def _info(codec, w, h, acodec="aac", ar=48000, ch=2, duration=10):
    return {
        "duration": duration,
        "video": {"codec": codec, "width": w, "height": h},
        "audio": {"codec": acodec, "sample_rate": ar, "channels": ch, "bit_rate": 128000},
    }


def test_encoder_mapping():
    assert resolve_encoder("hevc_nvenc", True) == "hevc_nvenc"
    assert resolve_encoder("hevc_nvenc", False) == "libx265"
    assert resolve_encoder("hevc", False) == "libx265"
    assert resolve_encoder("h264", True) == "h264_nvenc"
    assert resolve_encoder("h264_nvenc", False) == "libx264"


def test_presets():
    args = video_encode_args("hevc_nvenc", True, "fastest")
    assert args[:4] == ["-c:v", "hevc_nvenc", "-preset", "p1"]
    args = video_encode_args("hevc_nvenc", True, "balanced")
    assert "-preset" in args and "p4" in args
    args = video_encode_args("hevc_nvenc", True, "quality")
    assert "p6" in args
    args = video_encode_args("h264", False, "fastest")
    assert args[:4] == ["-c:v", "libx264", "-preset", "ultrafast"]
    assert speed_key_at(2) == "balanced"
    assert speed_index("quality") == 3
    assert len(SPEED_KEYS) == 4


def test_audio_copy():
    assert audio_encode_args({"codec": "aac"}) == ["-c:a", "copy"]
    assert audio_encode_args({"codec": "mp3"}) == ["-c:a", "aac", "-b:a", "128k"]
    assert audio_encode_args({"codec": ""}) == []
    assert audio_encode_args({"codec": "aac"}, force_reencode=True) == [
        "-c:a", "aac", "-b:a", "128k"]


def test_hwaccel():
    assert hwaccel_prefix(False) == []
    assert hwaccel_prefix(True, keep_on_gpu=True, vcodec="h264") == [
        "-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    assert hwaccel_prefix(True, vcodec="wmv3") == []
    assert hwaccel_prefix(True, vcodec="") == []
    assert hwaccel_prefix(True, vcodec="hevc")[:2] == ["-hwaccel", "cuda"]


def test_majority():
    infos = [
        ("a.mp4", _info("h264", 1920, 1080)),
        ("b.mp4", _info("h264", 1920, 1080)),
        ("c.mp4", _info("hevc", 1920, 1080)),
    ]
    key, count = pick_majority(infos)
    assert key[0] == "h264" and count == 2
    mixed = infos + [("d.mp4", _info("h264", 1920, 1080, acodec=""))]
    assert pick_majority(mixed)[0] is None
    unique = [
        ("a.mp4", _info("h264", 1920, 1080)),
        ("b.mp4", _info("hevc", 1280, 720)),
    ]
    assert pick_majority(unique)[0] is None


def test_merge_plan_copy_and_smart():
    ff = FFmpegWrapper("ffmpeg", "ffprobe")
    matched = [
        ("a.mp4", _info("h264", 1920, 1080, duration=5)),
        ("b.mp4", _info("h264", 1920, 1080, duration=7)),
    ]
    plan = ff.build_merge_plan(list(p for p, _ in matched), "out.mp4", matched, re_encode=False)
    assert len(plan["steps"]) == 1
    assert "-c" in plan["steps"][0]["cmd"] and "copy" in plan["steps"][0]["cmd"]

    mixed = matched + [("c.mp4", _info("hevc", 1920, 1080, duration=3))]
    paths = [p for p, _ in mixed]
    plan = ff.build_merge_plan(paths, "out.mp4", mixed, re_encode=True, use_nvenc=True, speed="fastest")
    assert len(plan["steps"]) == 2
    transcode = plan["steps"][0]["cmd"]
    assert "hevc_nvenc" not in transcode or "h264_nvenc" in transcode
    assert "-preset" in transcode and "p1" in transcode
    assert plan["steps"][1]["cmd"][-4] == "copy" or "copy" in plan["steps"][1]["cmd"]

    all_diff = [
        ("a.mp4", _info("h264", 1920, 1080)),
        ("b.mp4", _info("hevc", 1280, 720)),
    ]
    plan = ff.build_merge_plan(
        [p for p, _ in all_diff], "out.mp4", all_diff, re_encode=True, speed="balanced")
    assert any(c == "-filter_complex" for c in plan["steps"][0]["cmd"])
    assert "p4" in plan["steps"][0]["cmd"]


def test_compress_command():
    ff = FFmpegWrapper("ffmpeg", "ffprobe")
    cmd, info = ff.build_compress_command(
        "in.mp4", "out.mp4", 100, 60,
        codec="hevc_nvenc", use_nvenc=True, speed="fast",
        audio_info={"codec": "aac", "bit_rate": 128000},
        video_info={"codec": "h264"},
    )
    assert cmd[:5] == ["ffmpeg", "-y", "-hwaccel", "cuda", "-hwaccel_output_format"]
    assert "p3" in cmd
    assert info["audio_copy"] is True
    assert "-c:a" in cmd and "copy" in cmd
    assert resolve_encoder("hevc", False) in video_encode_args("hevc", False, "quality")


def test_ass_watermark():
    ass = build_ass(1920, 1080, 120, "", "测试水印", "#FF0000", 40, 0.3, 7)
    assert "[Events]" in ass
    assert r"\move(" in ass
    assert "测试水印" in ass
    assert _css_to_ass_color("#FF0000", 1.0).startswith("&H00")
    positions = generate_positions(90, 7, 1080)
    assert positions[0][0] == 0.0
    assert len(positions) >= 3
    probe = {
        "width": 1920, "height": 1080, "duration": 12, "codec": "h264",
        "audio": {"codec": "aac"},
    }
    cmd, dur, extras = build_command(
        "ffmpeg", "in.mp4", "out.mp4", os.path.join(ROOT, "msyh.ttc"), probe,
        speed="quality", use_nvenc=True,
    )
    try:
        assert dur == 12
        assert extras and extras[0].endswith(".ass")
        assert any("subtitles=" in c for c in cmd)
        assert "p6" in cmd
        assert "-hwaccel" in cmd and "cuda" in cmd
        joined = " ".join(cmd)
        assert "drawtext" not in joined
    finally:
        for p in extras:
            if os.path.exists(p):
                os.remove(p)


def test_filter_path_escape():
    escaped = escape_filter_path(r"C:\Temp\a b.ass")
    assert escaped.startswith("'")
    assert "\\:" in escaped or "C\\:" in escaped or "C:" not in escaped.replace("\\:", "")


def test_profile_key():
    assert profile_key(_info("H264", 1920, 1080))[0] == "h264"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    if failed:
        sys.exit(1)
    print(f"\n{len(tests)} passed")
