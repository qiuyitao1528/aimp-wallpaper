"""设置窗口排版改造的冒烟：逐页截图 + 保存链路验证（临时配置，不碰真实配置）。"""
import ctypes
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

from PIL import ImageGrab  # noqa: E402
import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

from aimp_wallpaper import config  # noqa: E402
from aimp_wallpaper.settings_gui import SettingsWindow  # noqa: E402

TMP = tempfile.mkdtemp(prefix="aimpwp_gui_")
cfg = dict(config.DEFAULTS)
cfg["output_dir"] = TMP

root = tk.Tk()
root.withdraw()
win = SettingsWindow(root, cfg)
root.update()

# 找到 Notebook（设置窗 Toplevel 的直接子控件里）
nb = None
for c in win.win.winfo_children():
    if isinstance(c, ttk.Notebook):
        nb = c
        break
assert nb is not None, "找不到 Notebook"

names = ["壁纸", "封面", "排版", "歌名", "歌手", "专辑", "歌曲信息", "面板", "系统"]
shots = []
toplevel = win.win
toplevel.deiconify()
toplevel.lift()
root.update()
time.sleep(0.3)
root.update()
for i, name in enumerate(names):
    nb.select(i)
    root.update_idletasks()
    root.update()
    time.sleep(0.25)
    root.update()
    x, y = toplevel.winfo_rootx(), toplevel.winfo_rooty()
    w, h = toplevel.winfo_width(), toplevel.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    p = os.path.join(TMP, f"tab_{i}_{name}.png")
    img.save(p)
    shots.append(p)

# 保存链路：把 CONFIG_PATH 指到临时文件再 _save
config.CONFIG_PATH = os.path.join(TMP, "config.json")
win._save()
ok_saved = os.path.exists(config.CONFIG_PATH)

# 关键变量存在性
missing = [a for a in ("bg_style_var", "pause_shrink_pct_var", "show_text_var", "lyr_side_var",
                       "lyr_gap_var", "vis_gap_var", "_info_tpl_var") if not hasattr(win, a)]
print("pages:", list(win._pages.keys()))
print("save_ok:", ok_saved, "missing_vars:", missing)
print("shots:", len(shots))
for p in shots:
    print("  ", p)
print("RESULT:", "ALL_PASS" if ok_saved and not missing else "FAILED")
toplevel.destroy()
root.destroy()
