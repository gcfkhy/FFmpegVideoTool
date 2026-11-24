# -*- coding: utf-8 -*-
"""从 assets/icon.jpg 生成 Windows 多尺寸 ICO。

旧脚本用 16x16 当底图再放大，资源管理器里会发糊。
这里从原图缩小出 16~256 各档，并去掉四周浅色底做成透明。
"""
import os
from collections import deque

from PIL import Image


ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "assets", "icon.jpg")
DST = os.path.join(ROOT, "assets", "icon.ico")
PREVIEW = os.path.join(ROOT, "assets", "icon_preview.png")
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
         (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]
PADDING_RATIO = 0.08


def _is_bg(pixel):
    r, g, b, a = pixel
    if a == 0:
        return True
    mx, mn = max(r, g, b), min(r, g, b)
    # JPEG 浅底不是纯白（例如 255,246,241），用高亮+低饱和判断
    return mn >= 210 and (mx - mn) <= 40


def knock_out_background(img):
    """从四边灌入，把连通浅底变透明，保留图标内部的白色播放键。"""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    seen = [[False] * h for _ in range(w)]
    q = deque()

    def push(x, y):
        if 0 <= x < w and 0 <= y < h and not seen[x][y] and _is_bg(px[x, y]):
            seen[x][y] = True
            q.append((x, y))

    for x in range(w):
        push(x, 0)
        push(x, h - 1)
    for y in range(h):
        push(0, y)
        push(w - 1, y)

    while q:
        x, y = q.popleft()
        px[x, y] = (0, 0, 0, 0)
        push(x - 1, y)
        push(x + 1, y)
        push(x, y - 1)
        push(x, y + 1)
    return img


def crop_to_content(img, pad_ratio=PADDING_RATIO):
    bbox = img.getbbox()
    if not bbox:
        return img
    l, t, r, b = bbox
    side = max(r - l, b - t)
    pad = max(int(side * pad_ratio), 1)
    side += pad * 2
    cx = (l + r) // 2
    cy = (t + b) // 2
    left = cx - side // 2
    top = cy - side // 2
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, (-left, -top))
    return canvas


def build_ico(src=SRC, dst=DST):
    prepared = crop_to_content(knock_out_background(Image.open(src)))
    frames = [
        prepared.resize(size, Image.Resampling.LANCZOS) for size in SIZES
    ]
    # 以 256 图为底保存，并把各档原图塞进 append_images，
    # 避免 Pillow 因底图太小跳过更大尺寸。
    frames[-1].save(
        dst,
        format="ICO",
        sizes=[frame.size for frame in frames],
        append_images=frames,
    )
    prepared.resize((256, 256), Image.Resampling.LANCZOS).save(PREVIEW)
    return dst, prepared


def ico_sizes(path):
    with open(path, "rb") as f:
        header = f.read(6)
    reserved, itype, count = __import__("struct").unpack("<HHH", header)
    return count


if __name__ == "__main__":
    path, prepared = build_ico()
    print(f"Wrote {path} ({os.path.getsize(path)} bytes), cropped {prepared.size}")
    print(f"ICO images: {ico_sizes(path)}")
    ico = Image.open(path)
    print("Pillow sizes:", sorted(ico.info.get("sizes", [])))
