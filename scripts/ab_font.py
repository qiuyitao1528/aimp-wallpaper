# -*- coding: utf-8 -*-
"""A/B：宋体 vs NotoSerifSC vs 默认雅黑 渲染同一文字，对比文字区像素差异。"""
import sys

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
from PIL import Image

from aimp_wallpaper import wallpaper, config

meta = {"title": "字体对比测试 ABC 123", "artist": "歌手", "album": ""}


def render(font_file, bold):
    cfg = dict(config.DEFAULTS)
    cfg["title_font_file"] = font_file
    cfg["title_bold"] = bold
    cfg["show_text"] = True
    img, anchor = wallpaper.render_poster(None, meta, 1920, 1080, cfg, want_anchor=True)
    return img, anchor


a, anchor = render("simsun.ttc", False)        # 宋体
b, _ = render("NotoSerifSC-VF.ttf", False)     # Noto Serif SC
c, _ = render(None, False)                     # 默认雅黑常规

# 裁标题区（文字右缘起、上下各 200px）转灰度比对
def crop(img, anchor):
    x, y = anchor
    return np.asarray(img.crop((x, y - 220, x + 900, y + 20)).convert("L"), dtype=np.int16)

ca, cb, cc = crop(a, anchor), crop(b, anchor), crop(c, anchor)
print("宋体 vs Noto   : 平均差", round(float(np.abs(ca - cb).mean()), 2), " 最大差", int(np.abs(ca - cb).max()))
print("宋体 vs 默认雅黑: 平均差", round(float(np.abs(ca - cc).mean()), 2), " 最大差", int(np.abs(ca - cc).max()))
print("Noto vs 默认雅黑: 平均差", round(float(np.abs(cb - cc).mean()), 2), " 最大差", int(np.abs(cb - cc).max()))
print("非零差异像素占比 宋体/Noto:", round(float((np.abs(ca - cb) > 8).mean()) * 100, 1), "%")
