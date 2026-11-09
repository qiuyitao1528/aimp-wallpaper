# -*- coding: utf-8 -*-
"""设置里加"切歌淡入过渡"开关与时长。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\settings_gui.py"
s = io.open(P, encoding="utf-8").read()

if "fade_var" in s:
    print("已存在，跳过")
    raise SystemExit

OLD = '''        self.cover_dy_var = combo(pg, "封面 Y 偏移(像素)", OFFSET_CHOICES,
                                  int(cfg.get("cover_offset_y", 0) or 0))'''
NEW = '''        self.cover_dy_var = combo(pg, "封面 Y 偏移(像素)", OFFSET_CHOICES,
                                  int(cfg.get("cover_offset_y", 0) or 0))
        self.fade_var = check(pg, "切歌时淡入过渡", cfg.get("fade_enabled", True))
        self.fade_ms_var = combo(pg, "过渡时长(毫秒)", [120, 160, 220, 300, 400],
                                 int(cfg.get("fade_ms", 220) or 220))'''
if OLD not in s:
    print("未匹配到封面 Y 偏移行")
    raise SystemExit
s = s.replace(OLD, NEW)

OLD2 = '''        self._int(self.cover_dy_var, "cover_offset_y", -2000, 2000)'''
NEW2 = '''        self._int(self.cover_dy_var, "cover_offset_y", -2000, 2000)
        self._int(self.fade_ms_var, "fade_ms", 60, 1500)
        self.cfg["fade_enabled"] = self.fade_var.get()'''
if OLD2 not in s:
    print("未匹配到保存行")
    raise SystemExit
s = s.replace(OLD2, NEW2)
io.open(P, "w", encoding="utf-8").write(s)
print("设置项已加：切歌淡入过渡 + 时长")
