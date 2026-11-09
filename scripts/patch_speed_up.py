# -*- coding: utf-8 -*-
"""切歌提速：收紧固定等待（轮询/去抖/封面首试），并给每次切换加耗时日志。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\aimp_api.py"
s = io.open(P, encoding="utf-8").read()

# 1) 轮询间隔 1000ms → 120ms（NOTIFY 缺席时也能快速发现换曲）
if "def __init__(self, poll_ms=1000):" in s:
    s = s.replace("def __init__(self, poll_ms=1000):", "def __init__(self, poll_ms=120):")

# 2) 去抖阈值 0.5s → 0.2s（仍要求连续两次一致，只是更快）
s = s.replace("            if time.time() - self._cand_since < 0.5:",
              "            if time.time() - self._cand_since < 0.2:")

# 3) 封面：首试 300ms → 80ms；快速重试 500ms → 150ms，窗口 2s → 1.5s
s = s.replace("        self._cover_next_try = now + 0.3\n        self._cover_fast_until = now + 2.0",
              "        self._cover_next_try = now + 0.08\n        self._cover_fast_until = now + 1.5")
s = s.replace('        self._cover_next_try = now + (0.5 if now < getattr(self, "_cover_fast_until", 0) else 1.0)',
              '        self._cover_next_try = now + (0.15 if now < getattr(self, "_cover_fast_until", 0) else 0.6)')

io.open(P, "w", encoding="utf-8").write(s)
print("aimp_api: 等待已收紧")

# ---------- 4) worker 加分段耗时日志 ----------
P = r"E:\aimp-wallpaper\aimp_wallpaper\__main__.py"
s = io.open(P, encoding="utf-8").read()
OLD = '''        cover = ipc.wait_cover(gen, timeout=12.0)  # 覆盖 10s 封面重试窗口
'''
NEW = '''        t_wait0 = time.monotonic()
        cover = ipc.wait_cover(gen, timeout=12.0)  # 覆盖 10s 封面重试窗口
        cover_ms = (time.monotonic() - t_wait0) * 1000
'''
if OLD in s:
    s = s.replace(OLD, NEW)
else:
    print("worker: 未找到封面等待行")

OLD2 = '''        if render(cover, snap, "切歌"):
            last_gen = gen'''
NEW2 = '''        t_render0 = time.monotonic()
        if render(cover, snap, "切歌"):
            render_ms = (time.monotonic() - t_render0) * 1000
            applog.log(f"[切歌] 耗时: 封面 {cover_ms:.0f}ms + 渲染换图 {render_ms:.0f}ms "
                       f"= {cover_ms + render_ms:.0f}ms")
            last_gen = gen'''
if OLD2 in s:
    s = s.replace(OLD2, NEW2)
else:
    print("worker: 未找到渲染行")
io.open(P, "w", encoding="utf-8").write(s)
print("__main__: 已加耗时日志")
