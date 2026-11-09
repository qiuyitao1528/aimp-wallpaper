# -*- coding: utf-8 -*-
"""撤掉自绘过渡：Windows 自身渐变已恢复，改为完全走系统默认。"""
import io
import os

ROOT = r"E:\aimp-wallpaper\aimp_wallpaper"

# ---------- wallpaper.py：去掉旧图快照与过渡块 ----------
P = ROOT + r"\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

# 1) 去掉快照采集
start = s.find("    # 切换前的桌面快照（用于\"旧图淡出\"过渡）")
if start < 0:
    start = s.find("    # 切换前的桌面快照")
end = s.find("    layers = []", start) if start >= 0 else -1
if start >= 0 and end > start:
    s = s[:start] + s[end:]

# 2) 去掉过渡块（从注释到 finally 结束）
start = s.find("    # 过渡（Win11 已不再给壁纸切换做渐变，这里自己画")
if start >= 0:
    end = s.find("    # 可视化面板锚点：屏幕坐标", start)
    BLOCK = '''    for m, path in zip(targets, paths):
        dw.SetWallpaper(m["id"], path)
    dw.SetPosition(DWPOS_FILL)
'''
    s = s[:start] + BLOCK + s[end:]

# 3) 清掉未用的常量
s = s.replace("_FADE_GRACE_S = 0.4  # 换图后保持覆盖层的时间（等 shell 真正刷到桌面）\n", "")
io.open(P, "w", encoding="utf-8").write(s)
print("wallpaper.py: 过渡相关已移除")

# ---------- config.py：去掉 fade 键 ----------
P = ROOT + r"\config.py"
s = io.open(P, encoding="utf-8").read()
for line in ('    "fade_enabled": True,       # 切歌时壁纸淡入过渡（Windows 自身已不做渐变）\n',
             '    "fade_ms": 220,             # 过渡时长(毫秒)\n'):
    s = s.replace(line, "")
io.open(P, "w", encoding="utf-8").write(s)
print("config.py: fade 键已移除")

# ---------- settings_gui.py：去掉过渡设置行 ----------
P = ROOT + r"\settings_gui.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace('''        self.fade_var = check(pg, "切歌时淡入过渡", cfg.get("fade_enabled", True))
        self.fade_ms_var = combo(pg, "过渡时长(毫秒)", [120, 160, 220, 300, 400],
                                 int(cfg.get("fade_ms", 220) or 220))
''', "")
s = s.replace('''        self._int(self.fade_ms_var, "fade_ms", 60, 1500)
        self.cfg["fade_enabled"] = self.fade_var.get()
''', "")
io.open(P, "w", encoding="utf-8").write(s)
print("settings_gui.py: 过渡设置已移除")

# ---------- 删除 fade.py ----------
f = ROOT + r"\fade.py"
if os.path.exists(f):
    os.remove(f)
    print("fade.py 已删除")
