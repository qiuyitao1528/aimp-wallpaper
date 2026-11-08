# -*- coding: utf-8 -*-
"""量化加粗效果：用户当前配置（思源宋体 OTF）+ 默认字体，加粗开/关的着墨量对比。"""
import sys

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
from PIL import Image

from aimp_wallpaper import wallpaper, config

FONT = r"C:\Users\Administrator\AppData\Local\Microsoft\Windows\Fonts\SourceHanSerifCN-Regular-1.otf"
meta = {"title": "歌名加粗对比测试", "artist": "", "album": ""}


def ink(title_bold, font_file, stroke_note=""):
    cfg = dict(config.DEFAULTS)
    cfg["title_font_file"] = font_file
    cfg["title_bold"] = title_bold
    cfg["sub_font_file"] = None
    img, anchor = wallpaper.render_poster(None, meta, 1920, 1080, cfg, want_anchor=True)
    x, y = anchor
    crop = np.asarray(img.crop((x, y - 240, x + 1000, y + 40)).convert("L"))
    return int((crop > 140).sum())  # 亮像素=文字着墨


print(f"自定义思源宋体 加粗OFF 着墨: {ink(False, FONT)}")
print(f"自定义思源宋体 加粗ON  着墨: {ink(True, FONT)}")
print(f"默认雅黑       加粗OFF 着墨: {ink(False, None)}")
print(f"默认雅黑       加粗ON  着墨: {ink(True, None)}")
