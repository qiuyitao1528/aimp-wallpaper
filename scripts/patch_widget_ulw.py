# -*- coding: utf-8 -*-
"""给回退后的代码补上覆盖窗口协同（控件+面板共用），并接入控件开关。"""
import io
import re

ROOT = r"E:\aimp-wallpaper\aimp_wallpaper"

# ---------- 1. desktop.py：加 register_overlay / seat_overlays ----------
p = ROOT + r"\desktop.py"
s = io.open(p, encoding="utf-8").read()
if "def seat_overlays" not in s:
    s = s.rstrip() + '''


# ---------- 桌面层覆盖窗口协同：Progman 压到所有覆盖窗口之下 ----------

_overlays: list[int] = []
_NOMOVE_NOSIZE_NOACTIVATE = 0x2 | 0x1 | 0x10


def register_overlay(hwnd) -> None:
    """登记桌面层覆盖窗口（控件/频谱面板/歌词）。"""
    h = int(hwnd)
    if h not in _overlays:
        _overlays.append(h)


def seat_overlays() -> bool:
    """把 Progman 插到所有已登记覆盖窗口之下；z-order 已正确时零写操作。"""
    progman = user32.FindWindowW("Progman", None)
    if not progman or not _overlays:
        return False
    if user32.GetWindow(progman, GW_HWNDPREV) == HWND_T(_overlays[0]):
        return True
    user32.SetWindowPos(progman, HWND_T(_overlays[0]), 0, 0, 0, 0, _NOMOVE_NOSIZE_NOACTIVATE)
    for h in _overlays[1:]:
        user32.SetWindowPos(HWND_T(h), HWND_T(_overlays[0]), 0, 0, 0, 0,
                            _NOMOVE_NOSIZE_NOACTIVATE)
    return True
'''
    io.open(p, "w", encoding="utf-8").write(s)
    print("desktop.py: 已加 register_overlay/seat_overlays")
else:
    print("desktop.py: 已有，跳过")

# ---------- 2. vis_panel.py：seat 改走统一协同 ----------
p = ROOT + r"\vis_panel.py"
s = io.open(p, encoding="utf-8").read()
m = re.search(r"    def _seat_above_desktop\(self\):.*?\n\n", s, re.S)
if m and "desktop.seat_overlays()" not in s:
    new = '''    def _seat_above_desktop(self):
        """把 Progman 压到所有覆盖窗口（面板/控件）之下；顺带处理被最小化。
        z-order 已正确时零跨进程写操作（GetWindow 是无阻塞查询）。"""
        if desktop.user32.IsIconic(self._hwnd):
            desktop.user32.ShowWindow(self._hwnd, 4)  # SW_SHOWNOACTIVATE
        desktop.register_overlay(self._hwnd)
        desktop.seat_overlays()

'''
    s = s[:m.start()] + new + s[m.end():]
    io.open(p, "w", encoding="utf-8").write(s)
    print("vis_panel.py: seat 已改走统一协同")
else:
    print("vis_panel.py: 跳过")

# ---------- 3. config.py：加 widget_hidden ----------
p = ROOT + r"\config.py"
s = io.open(p, encoding="utf-8").read()
if '"widget_hidden"' not in s:
    s = s.replace('    "vis_hidden": False,',
                  '    "vis_hidden": False,\n'
                  '    "widget_hidden": False,     # 隐藏桌面音乐控件')
    io.open(p, "w", encoding="utf-8").write(s)
    print("config.py: 已加 widget_hidden")
else:
    print("config.py: 已有，跳过")

# ---------- 4. tray.py：加控件开关菜单 ----------
p = ROOT + r"\tray.py"
s = io.open(p, encoding="utf-8").read()
if "on_toggle_widget" not in s:
    s = s.replace("def __init__(self, root, on_settings, on_toggle_vis, on_restore, on_quit):",
                  "def __init__(self, root, on_settings, on_toggle_vis, on_toggle_widget,\n"
                  "                 on_restore, on_quit):")
    s = s.replace('pystray.MenuItem("恢复原壁纸", lambda: post("恢复原壁纸", on_restore)),',
                  'pystray.MenuItem("显示 / 隐藏控件", lambda: post("开关控件", on_toggle_widget)),\n'
                  '                pystray.MenuItem("恢复原壁纸", lambda: post("恢复原壁纸", on_restore)),')
    io.open(p, "w", encoding="utf-8").write(s)
    print("tray.py: 已加控件开关")
else:
    print("tray.py: 已有，跳过")

# ---------- 5. __main__.py：接 toggle_widget ----------
p = ROOT + r"\__main__.py"
s = io.open(p, encoding="utf-8").read()
if "toggle_widget" not in s:
    s = s.replace('''    def restore_wp():''',
                  '''    def toggle_widget():
        cfg["widget_hidden"] = not bool(cfg.get("widget_hidden"))
        config.save(cfg)
        applog.log(f"控件显隐切换: widget_hidden={cfg.get('widget_hidden')}")

    def restore_wp():''')
    s = s.replace("tray = Tray(root, on_settings=open_settings, on_toggle_vis=toggle_vis,",
                  "tray = Tray(root, on_settings=open_settings, on_toggle_vis=toggle_vis,\n"
                  "                on_toggle_widget=toggle_widget,")
    io.open(p, "w", encoding="utf-8").write(s)
    print("__main__.py: 已接 toggle_widget")
else:
    print("__main__.py: 已有，跳过")

# ---------- 6. settings_gui.py：加控件开关 ----------
p = ROOT + r"\settings_gui.py"
s = io.open(p, encoding="utf-8").read()
if "widget_var" not in s:
    s = s.replace('''        ttk.Label(self.win, text="字体").grid''',
                  '''        self.widget_var = tk.BooleanVar(value=not bool(cfg.get("widget_hidden")))
        ttk.Checkbutton(self.win, text="显示桌面音乐控件", variable=self.widget_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        ttk.Label(self.win, text="字体").grid''')
    s = s.replace('        self.cfg["restore_on_quit"] = self.restore_var.get()',
                  '        self.cfg["restore_on_quit"] = self.restore_var.get()\n'
                  '        self.cfg["widget_hidden"] = not self.widget_var.get()')
    io.open(p, "w", encoding="utf-8").write(s)
    print("settings_gui.py: 已加控件开关")
else:
    print("settings_gui.py: 已有，跳过")

print("done")
