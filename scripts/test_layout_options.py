# -*- coding: utf-8 -*-
"""布局参数验证：封面偏移/缩放、文字偏移/水平对齐/垂直对齐 是否真实生效。"""
import io
import sys

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
from PIL import Image

from aimp_wallpaper import config, wallpaper

meta = {"title": "布局测试标题", "artist": "歌手", "album": "专辑"}
W, H = 1920, 1080


def render(**over):
    cfg = dict(config.DEFAULTS)
    cfg.update(over)
    img, anchor = wallpaper.render_poster(None, meta, W, H, cfg, want_anchor=True)
    return img, anchor


def cover_bbox(img):
    """封面占位框（深灰 40,44,58）的包围盒。"""
    a = np.asarray(img)
    mask = (np.abs(a[:, :, 0].astype(int) - 40) < 8) & (np.abs(a[:, :, 1].astype(int) - 44) < 8) \
        & (np.abs(a[:, :, 2].astype(int) - 58) < 8)
    ys, xs = np.nonzero(mask)
    return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None


def text_ink(img, y0=0, y1=H):
    """文字亮像素的 x 范围与质心。"""
    a = np.asarray(img.convert("L"))[y0:y1]
    ys, xs = np.nonzero(a > 200)
    if not len(xs):
        return None
    return {"x0": int(xs.min()), "x1": int(xs.max()), "cx": float(xs.mean()),
            "y0": int(ys.min()) + y0, "y1": int(ys.max()) + y0}


base_img, base_anchor = render()
b0 = cover_bbox(base_img)
t0 = text_ink(base_img)
print("基准: 封面", b0, "| 文字 x", (t0["x0"], t0["x1"]), "y", (t0["y0"], t0["y1"]))
fails = []

# 1. 封面 X 偏移 +100
img, _ = render(cover_offset_x=100)
b1 = cover_bbox(img)
print("封面X+100:", b1)
if not (b1[0] - b0[0] == 100):
    fails.append("cover_offset_x")

# 2. 封面 Y 偏移 +60
img, _ = render(cover_offset_y=60)
b2 = cover_bbox(img)
print("封面Y+60:", b2, "| 位移:", b2[1] - b0[1])
if not (b2[1] - b0[1] == 60):
    fails.append("cover_offset_y")

# 3. 封面缩放 0.6 → 尺寸应变小
img, _ = render(cover_scale=0.6)
b3 = cover_bbox(img)
w0, w3 = b0[2] - b0[0], b3[2] - b3[0]
print("封面缩放0.6: 宽", w0, "->", w3)
if not (w3 < w0 * 0.75):
    fails.append("cover_scale")

# 4. 文字水平对齐：左/中/右 的亮区范围应依次右移
ink_left = text_ink(render(text_align="left")[0])
ink_center = text_ink(render(text_align="center")[0])
ink_right = text_ink(render(text_align="right")[0])
print("对齐 left x0:", ink_left["x0"], "| center x0:", ink_center["x0"], "| right x0:", ink_right["x0"])
if not (ink_left["x0"] < ink_center["x0"] < ink_right["x0"]):
    fails.append("text_align")

# 5. 文字垂直对齐 top/center/bottom
vy_top = text_ink(render(text_valign="top")[0])["y1"]
vy_center = text_ink(render(text_valign="center")[0])["y1"]
vy_bottom = text_ink(render(text_valign="bottom")[0])["y1"]
print("垂直对齐 底边 y: top", vy_top, "| center", vy_center, "| bottom", vy_bottom)
if not (vy_top < vy_center < vy_bottom):
    fails.append("text_valign")

# 6. 文字 X/Y 偏移
img, _ = render(text_offset_x=80)
if text_ink(img)["x0"] - t0["x0"] < 60:
    fails.append("text_offset_x")
img, _ = render(text_offset_y=50)
if text_ink(img)["y0"] - t0["y0"] < 30:
    fails.append("text_offset_y")
print("文字偏移 OK" if "text_offset_x" not in fails and "text_offset_y" not in fails else "文字偏移 FAIL")

# 7. 锚点随布局变化（可视化面板跟随）
_, a_off = render(text_offset_y=100)
print("锚点基准", base_anchor, "| 文字Y+100 后", a_off)
if a_off[1] - base_anchor[1] < 90:
    fails.append("anchor 跟随")

print("=== 结果:", "全部通过" if not fails else f"失败 {fails}", "===")
