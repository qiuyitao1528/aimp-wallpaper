# -*- coding: utf-8 -*-
"""移除桌面音乐控件（widget）相关全部接线，保留频谱面板。"""
import io
import os

ROOT = r"E:\aimp-wallpaper\aimp_wallpaper"

# ---------- __main__.py ----------
p = ROOT + r"\__main__.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("from .vis_panel import VisPanel\nfrom .widget import Widget\n",
              "from .vis_panel import VisPanel\n")
s = s.replace("""    root = tk.Tk()
    root.title("AIMP Wallpaper")
    root.report_callback_exception = lambda t, v, tb: applog.log_exc("Tk 回调异常:\\n", t, v, tb)
""",
              """    root = tk.Tk()
    root.title("AIMP Wallpaper")
    root.withdraw()  # 无可见主窗（界面=频谱面板+托盘）
    root.report_callback_exception = lambda t, v, tb: applog.log_exc("Tk 回调异常:\\n", t, v, tb)
""")
s = s.replace("    Widget(root, ipc, cfg, show_vis=show_vis)\n", "")
s = s.replace("""    def toggle_widget():
        cfg["widget_hidden"] = not bool(cfg.get("widget_hidden"))
        config.save(cfg)
        applog.log(f"控件显隐切换: widget_hidden={cfg.get('widget_hidden')}")

""", "")
s = s.replace("""    tray = Tray(root, on_settings=open_settings, on_toggle_vis=toggle_vis,
                on_toggle_widget=toggle_widget,""",
              """    tray = Tray(root, on_settings=open_settings, on_toggle_vis=toggle_vis,""")
io.open(p, "w", encoding="utf-8").write(s)
print("__main__.py 已移除控件接线")

# ---------- tray.py ----------
p = ROOT + r"\tray.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("""def __init__(self, root, on_settings, on_toggle_vis, on_toggle_widget,
                 on_restore, on_quit):""",
              "def __init__(self, root, on_settings, on_toggle_vis, on_restore, on_quit):")
s = s.replace('                pystray.MenuItem("显示 / 隐藏控件", lambda: post("开关控件", on_toggle_widget)),\n', "")
io.open(p, "w", encoding="utf-8").write(s)
print("tray.py 已移除控件菜单")

# ---------- settings_gui.py ----------
p = ROOT + r"\settings_gui.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("""        self.widget_var = tk.BooleanVar(value=not bool(cfg.get("widget_hidden")))
        ttk.Checkbutton(self.win, text="显示桌面音乐控件", variable=self.widget_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

""", "")
s = s.replace('        self.cfg["widget_hidden"] = not self.widget_var.get()\n', "")
io.open(p, "w", encoding="utf-8").write(s)
print("settings_gui.py 已移除控件选项")

# ---------- config.py：去掉控件相关键 ----------
p = ROOT + r"\config.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace('    "widget_hidden": False,     # 隐藏桌面音乐控件\n', "")
s = s.replace('    # 小部件\n    "widget_alpha": 235,        # 0~255\n    "widget_width": 460,\n    "widget_pos": None,         # [x, y] 屏幕坐标；None=底部居中\n', "")
io.open(p, "w", encoding="utf-8").write(s)
print("config.py 已移除控件配置键")

# ---------- 删除 widget.py ----------
w = ROOT + r"\widget.py"
if os.path.exists(w):
    os.remove(w)
    print("widget.py 已删除")
print("done")
