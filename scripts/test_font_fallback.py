# -*- coding: utf-8 -*-
"""验证字体回退：分段结果 + 渲染结果里方框像素数量对比。"""
import io
import sys

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
from PIL import Image, ImageDraw

from aimp_wallpaper import config, wallpaper

TITLE = "\u5c0f\u5c0f\u5947\u8ff9\uff08\u5c1a\u672a\u53d1\u5e03 (\u0e51\u2022\u0300\u1d17\u002d \u0029\u2727\u2729\u00b0\uff61\u22c6\uff01\uff09"
print("测试标题 codepoints:", " ".join(f"U+{ord(c):04X}" for c in TITLE))

noto = wallpaper._load_font(True, 60, "NotoSerifSC-VF.ttf")[0]
runs = wallpaper._text_runs(TITLE, noto)
print("\n分段结果:")
for chunk, f in runs:
    fname = f.path.rsplit("\\", 1)[-1]
    print("  ", fname, "|", " ".join(f"U+{ord(c):04X}" for c in chunk))

fallback_used = any(f is not noto for _c, f in runs)
print("\n是否用到了回退字体:", fallback_used)

# 渲染整张海报，统计"方框"特征像素（.notdef 白框：空心矩形，边框像素多）
cfg = dict(config.DEFAULTS)
cfg["title_font_file"] = "NotoSerifSC-VF.ttf"
cfg["sub_font_file"] = "NotoSerifSC-VF.ttf"
meta = {"title": TITLE, "artist": "Test", "album": ""}
img, anchor = wallpaper.render_poster(None, meta, 1920, 1080, cfg, want_anchor=True)
x, y = anchor
crop = img.crop((x, y - 240, min(1920, x + 900), y + 10))
crop.save(r"E:\aimp-wallpaper\scripts\fallback_check.png")
a = np.asarray(crop.convert("L"))
print("文字区尺寸:", crop.size, "| 亮像素:", int((a > 180).sum()))
print("已保存 scripts/fallback_check.png")
