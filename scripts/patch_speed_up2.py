# -*- coding: utf-8 -*-
"""二次提速：封面重试加密（60ms 一档，前 0.8s）+ 显示器列表短缓存。"""
import io

# ---------- 1. 封面重试节奏 ----------
P = r"E:\aimp-wallpaper\aimp_wallpaper\aimp_api.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace("        self._cover_next_try = now + 0.08\n        self._cover_fast_until = now + 1.5",
              "        self._cover_next_try = now + 0.05\n        self._cover_fast_until = now + 0.8")
s = s.replace('        self._cover_next_try = now + (0.15 if now < getattr(self, "_cover_fast_until", 0) else 0.6)',
              '        self._cover_next_try = now + (0.06 if now < getattr(self, "_cover_fast_until", 0) else 0.5)')
io.open(P, "w", encoding="utf-8").write(s)
print("封面重试：50ms 首试 + 60ms 密集重试(0.8s) + 0.5s 兜底")

# ---------- 2. 显示器列表短缓存 ----------
P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()
OLD = '''    dw = _get_wallpaper_com()
    monitors = []
    count = dw.GetMonitorDevicePathCount()'''
NEW = '''    global _MON_CACHE
    now = time.monotonic()
    if _MON_CACHE and now - _MON_CACHE[0] < 10.0:
        return [dict(m) for m in _MON_CACHE[1]]
    dw = _get_wallpaper_com()
    monitors = []
    count = dw.GetMonitorDevicePathCount()'''
if OLD in s and "_MON_CACHE" not in s:
    s = s.replace(OLD, NEW, 1)
    s = s.replace('''        if w > 0 and h > 0:
            monitors.append({"id": mid, "w": w, "h": h, "left": int(rc.left), "top": int(rc.top)})
    return monitors''',
'''        if w > 0 and h > 0:
            monitors.append({"id": mid, "w": w, "h": h, "left": int(rc.left), "top": int(rc.top)})
    if monitors:  # 缓存 10s：显示器很少变，省掉每次渲染的 COM 往返
        _MON_CACHE = (now, monitors)
    return [dict(m) for m in monitors]''')
    s = s.replace("def get_monitors() -> list[dict]:", "_MON_CACHE: tuple | None = None\n\n\ndef get_monitors() -> list[dict]:", 1)
    io.open(P, "w", encoding="utf-8").write(s)
    print("显示器列表：已加 10s 缓存")
else:
    print("显示器缓存：" + ("已存在" if "_MON_CACHE" in s else "未匹配"))
