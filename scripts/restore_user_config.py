# -*- coding: utf-8 -*-
"""恢复用户真实配置：自定义字体 + 真正的原壁纸记录（测试覆盖事故修复）。"""
import io
import json
import os

P = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "config.json")
USER_FONTS = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Windows", "Fonts")
d = json.load(io.open(P, encoding="utf-8"))

serif = os.path.join(USER_FONTS, "SourceHanSerifCN-Regular-1.otf")
sans = os.path.join(USER_FONTS, "SourceHanSansCN-Medium.ttf")
if os.path.exists(serif):
    d["title_font_file"] = serif
if os.path.exists(sans):
    d["sub_font_file"] = sans
d["original_wallpaper"] = r"E:\新建文件夹\微信图片_202307272047361.jpg"
d["original_position"] = 4
json.dump(d, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("字体:", d["title_font_file"], "|", d["sub_font_file"])
print("原壁纸:", d["original_wallpaper"], "| 存在:", os.path.exists(d["original_wallpaper"]))
