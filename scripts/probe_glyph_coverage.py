# -*- coding: utf-8 -*-
"""验证：缺字形检测方法 + 各系统字体对特殊字符的覆盖。"""
import sys

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
from PIL import ImageFont

FONTS = r"C:\Windows\Fonts"


def load(name, size=48):
    return ImageFont.truetype(FONTS + "\\" + name, size)


def mask_sig(font, ch):
    m = font.getmask(ch, mode="L")
    data = m.tobytes() if hasattr(m, "tobytes") else np.asarray(m).tobytes()
    return (m.size, data)


def missing(font, ch):
    return mask_sig(font, ch) == mask_sig(font, "\uffff")


CHARS = [
    ("THAI_0E51", "\u0e51"),
    ("STAR_2727", "\u2727"),
    ("STAR_2729", "\u2729"),
    ("STAR_22C6", "\u22c6"),
    ("PHON_1D17", "\u1d17"),
    ("HALFW_FF61", "\uff61"),
    ("BULLET", "\u2022"),
    ("DEGREE", "\u00b0"),
    ("CJK", "\u5c0f"),
]

primary = load("NotoSerifSC-VF.ttf")
print("primary NotoSerifSC missing:")
for name, ch in CHARS:
    print("  ", name, missing(primary, ch))

print("coverage by candidate fonts:")
for cand in ("msyh.ttc", "tahoma.ttf", "seguisym.ttf", "simsun.ttc", "segoeui.ttf"):
    try:
        f = load(cand)
    except Exception as e:
        print("  ", cand, "load failed:", e)
        continue
    cover = [n for n, ch in CHARS if not missing(f, ch)]
    print("  ", cand, "->", cover)
