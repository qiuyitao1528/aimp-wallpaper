# -*- coding: utf-8 -*-
"""布局参数验证：封面偏移/缩放、文字偏移/水平对齐/垂直对齐。
封面测量用真实封面图 + 关闭文字，避免与背景渐变、白色文字混淆。"""
import io
import sys

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
from PIL import Image

from aimp_wallpaper import config, wallpaper

meta = {"title": "布局测试标题", "artist": "歌手", "album": "专辑"}
W, H = 1920, 1080
_buf = io.BytesIO()
Image.new("RGB", (400, 400), (255, 255, 255)).save(_buf, "PNG")
COVER = _buf.getvalue()


def img_of(cover=False, **over):
    cfg = dict(config.DEFAULTS)
    cfg.update(over)
    if cover:
        cfg["show_text"] = False
    return wallpaper.render_poster(COVER if cover else None, meta, W, H, cfg, want_anchor=True)


def cover_bbox(img):
    a = np.asarray(img)
    m = (a[:, :, 0] > 245) & (a[:, :, 1] > 245) & (a[:, :, 2] > 245)
    ys, xs = np.nonzero(m)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def text_ink(img):
    a = np.asarray(img.convert("L"))
    ys, xs = np.nonzero(a > 200)
    return {"x0": int(xs.min()), "y0": int(ys.min()), "y1": int(ys.max())}


fails = []

# ---- 封面：真实封面 + 无文字 ----
b0 = cover_bbox(img_of(cover=True)[0])
print("封面基准:", b0, "→", b0[2] - b0[0], "x", b0[3] - b0[1])
b1 = cover_bbox(img_of(cover=True, cover_offset_x=100)[0])
b2 = cover_bbox(img_of(cover=True, cover_offset_y=60)[0])
b3 = cover_bbox(img_of(cover=True, cover_scale=0.5)[0])
print("X+100 位移:", b1[0] - b0[0], "| Y+60 位移:", b2[1] - b0[1],
      "| 缩放0.5:", b3[2] - b3[0], "x", b3[3] - b3[1])
if b1[0] - b0[0] != 100:
    fails.append("cover_offset_x")
if b2[1] - b0[1] != 60:
    fails.append("cover_offset_y")
if abs((b3[2] - b3[0]) - (b0[2] - b0[0]) * 0.5) > 3:
    fails.append("cover_scale")

# ---- 文字：无封面（占位框不参与白色测量）----
t0 = text_ink(img_of()[0])
ink_l = text_ink(img_of(text_align="left")[0])
ink_c = text_ink(img_of(text_align="center")[0])
ink_r = text_ink(img_of(text_align="right")[0])
print("对齐 x0: left", ink_l["x0"], "center", ink_c["x0"], "right", ink_r["x0"])
if not (ink_l["x0"] < ink_c["x0"] < ink_r["x0"]):
    fails.append("text_align")

vy = [text_ink(img_of(text_valign=v)[0])["y1"] for v in ("top", "center", "bottom")]
print("垂直对齐底边:", vy)
if not (vy[0] < vy[1] < vy[2]):
    fails.append("text_valign")

if text_ink(img_of(text_offset_x=80)[0])["x0"] - t0["x0"] < 60:
    fails.append("text_offset_x")
if text_ink(img_of(text_offset_y=50)[0])["y0"] - t0["y0"] < 30:
    fails.append("text_offset_y")

_, a0 = img_of()
_, a1 = img_of(text_offset_y=100)
print("锚点:", a0, "→", a1)
if a1[1] - a0[1] < 90:
    fails.append("anchor")

print("=== 结果:", "全部通过" if not fails else f"失败 {fails}", "===")
