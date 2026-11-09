# -*- coding: utf-8 -*-
"""修 bug：歌手与专辑同名时副行只显示一行（原逻辑把同名专辑当重复去掉了）。
改为专辑名非空就显示，不再做同名去重。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()
OLD = "            sub_entries = [artist] + ([album] if album and album != artist else [])"
NEW = ("            # 歌手/专辑同名也各占一行（此前同名被当重复吞掉，用户报为 bug）\n"
       "            sub_entries = [artist] + ([album] if album else [])")
if OLD in s:
    s = s.replace(OLD, NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("已修：同名不再去重")
else:
    print("未找到目标行")
