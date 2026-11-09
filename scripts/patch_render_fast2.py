# -*- coding: utf-8 -*-
"""亮度/饱和度调整挪到小图（4x 更少的像素），放大后再算等价于先算。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(4, cfg["blur_radius"]) / 4.0))
        bg = bg.resize((w, h), Image.BILINEAR)
        bg = ImageEnhance.Brightness(bg).enhance(cfg["darken"])
        bg = ImageEnhance.Color(bg).enhance(0.9)'''
NEW = '''        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(4, cfg["blur_radius"]) / 4.0))
        # 亮度/饱和度是逐像素运算，在小图上做与大图等价（省 ~12ms）
        bg = ImageEnhance.Brightness(bg).enhance(cfg["darken"])
        bg = ImageEnhance.Color(bg).enhance(0.9)
        bg = bg.resize((w, h), Image.BILINEAR)'''
if OLD in s:
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("已挪到小图")
else:
    print("未匹配")
