# -*- coding: utf-8 -*-
"""诊断字体回退：读用户 config 的字体键，逐候选路径试加载，打印真实报错。"""
import json
import os
import sys

sys.path.insert(0, r"E:\aimp-wallpaper")

from PIL import ImageFont

p = r"C:\Users\Administrator\AppData\Local\aimp-wallpaper\config.json"
d = json.load(open(p, encoding="utf-8"))
print("title_font_file =", repr(d.get("title_font_file")))
print("sub_font_file   =", repr(d.get("sub_font_file")))

user_fonts = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
for key in ("title_font_file", "sub_font_file"):
    f = d.get(key)
    if not f:
        continue
    cands = [f, os.path.join(r"C:\Windows\Fonts", f), os.path.join(user_fonts, f)]
    hit = False
    for cand in cands:
        if os.path.exists(cand):
            hit = True
            print(f"{key}: 文件存在 {cand}")
            try:
                font = ImageFont.truetype(cand, 60)
                print("  加载 OK:", font.path)
            except Exception as e:
                print(f"  加载失败: {type(e).__name__}: {e}")
            break
    if not hit:
        print(f"{key}: 所有候选路径都不存在! 候选={cands}")
