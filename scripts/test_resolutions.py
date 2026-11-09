# -*- coding: utf-8 -*-
"""多分辨率兼容性矩阵：分辨率 × 封面宽高比 × 缩放倍率 × 缩放基准。

验证每组合：渲染不崩、文字不越屏幕右缘/下缘、锚点在屏内、封面边界正常。
运行：uv run python -I scripts/test_resolutions.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from aimp_wallpaper import config, wallpaper  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILS.append(name)


def synth(aspect):
    """aspect: 'square'/'wide'/'tall' → 合成封面（含亮块与暗角，覆盖各种像素场景）。"""
    size = {"square": (900, 900), "wide": (1600, 800), "tall": (800, 1600)}[aspect]
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(size[1]):
        d.line([(0, y), (size[0], y)], fill=(int(255 * y / size[1]), 80, 255 - int(120 * y / size[1])))
    ew, eh = size[0] // 2, size[1] // 2
    d.ellipse([size[0] // 2 - ew // 2, size[1] // 2 - eh // 2,
               size[0] // 2 + ew // 2, size[1] // 2 + eh // 2], fill=(255, 220, 120))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


META = {"title": "Cry For Me (feat. Ami) (为我哭泣) [Live]", "artist": "Michita",
        "album": "Pureness Deluxe Edition Remastered",
        "filename": "", "duration_ms": 200000}
RESOLUTIONS = [(1920, 1080), (2560, 1440), (3840, 2160), (3440, 1440), (2560, 1080), (1080, 1920)]
ASPECTS = ("square", "wide", "tall")

n = 0
for (w, h) in RESOLUTIONS:
    for aspect in ASPECTS:
        cover = synth(aspect)
        for scale, anchor in ((1.0, "left"), (1.5, "right"), (1.2, "center"), (1.0, "center_bound")):
            cfg = dict(config.DEFAULTS)
            cfg.update(bg_style="blur", blur_radius=60, darken=0.75, show_text=True,
                       theme_night_follow=False, cover_scale=scale, cover_anchor=anchor,
                       line_order=["info", "title", "artist", "album"])
            n += 1
            tag = f"{w}x{h}/{aspect}/x{scale}/{anchor}"
            try:
                img, anch = wallpaper.render_poster(cover, META, w, h, cfg, want_anchor=True)
            except Exception as e:
                check(f"render {tag}", False, repr(e)[:120])
                continue
            a = np.asarray(img, dtype=np.int16)
            ok_size = img.size == (w, h)
            # 文字不越界：文本区（锚点 tx 之右）的亮像素不得到达屏幕最右/最下 2px
            bright = (a > 235).all(axis=2)
            tx = anch[0]
            xs = np.where(bright.any(axis=0))[0]
            text_xs = xs[xs >= tx] if len(xs) else np.array([0])
            ys = np.where(bright.any(axis=1))[0]
            ok_right = len(text_xs) == 0 or int(text_xs.max()) <= w - 3
            ok_bottom = len(ys) == 0 or int(ys.max()) <= h - 3
            ok_anchor = 0 <= anch[0] < w and 0 <= anch[1] < h
            check(f"render {tag}", ok_size and ok_right and ok_bottom and ok_anchor,
                  f"tx={anch[0]} text_max_x={int(text_xs.max()) if len(text_xs) else -1} "
                  f"max_y={int(ys.max()) if len(ys) else -1}")

print(f"\n组合总数: {n}")
print("RESULT:", "ALL_PASS" if not FAILS else f"FAILED={FAILS}")
sys.exit(1 if FAILS else 0)
