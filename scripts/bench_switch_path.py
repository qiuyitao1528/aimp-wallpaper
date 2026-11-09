# -*- coding: utf-8 -*-
"""测量切歌链路各段耗时（不含系统换图延迟）。"""
import io
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
from PIL import Image

from aimp_wallpaper import config, wallpaper

W, H = 1920, 1080
arr = (np.random.rand(700, 700, 3) * 255).astype("uint8")
buf = io.BytesIO()
Image.fromarray(arr).save(buf, "JPEG", quality=90)
cover = buf.getvalue()
meta = {"title": "小小奇迹（尚未发布 (๑•̀ㅂ•́) ✧✩°｡⋆！）", "artist": "潮汐先约电台/飞行雪绒", "album": "Wuthering Waves OST 飞向春天"}

cfg = dict(config.DEFAULTS)
cfg["title_font_file"] = r"C:\Windows\Fonts\NotoSerifSC-VF.ttf"

# 冷启动第一次（含字体/字形缓存填充）
t0 = time.perf_counter()
img, anchor = wallpaper.render_poster(cover, meta, W, H, cfg, want_anchor=True)
cold = (time.perf_counter() - t0) * 1000

# 热态（不同封面 → 背景缓存失效，相当于每首歌的常态）
times = []
save_times = {0: [], 1: [], 6: []}
for i in range(5):
    buf2 = io.BytesIO()
    Image.fromarray((np.random.rand(700, 700, 3) * 255).astype("uint8")).save(buf2, "JPEG", quality=90)
    cb = buf2.getvalue()
    t = time.perf_counter()
    img, _ = wallpaper.render_poster(cb, meta, W, H, cfg, want_anchor=True)
    times.append((time.perf_counter() - t) * 1000)
    for lvl in (0, 1, 6):
        p = rf"C:\Users\Administrator\AppData\Local\Temp\bench_{lvl}.png"
        t = time.perf_counter()
        img.save(p, "PNG", optimize=False, compress_level=lvl)
        save_times[lvl].append((time.perf_counter() - t) * 1000)

import os
for lvl in (0, 1, 6):
    p = rf"C:\Users\Administrator\AppData\Local\Temp\bench_{lvl}.png"
    print(f"PNG 压缩级别 {lvl}: 存盘 {np.mean(save_times[lvl]):.0f}ms | 文件 {os.path.getsize(p) / 1048576:.1f}MB")
    os.remove(p)
print(f"render_poster 冷启动: {cold:.0f}ms | 热态均值: {np.mean(times):.0f}ms")
