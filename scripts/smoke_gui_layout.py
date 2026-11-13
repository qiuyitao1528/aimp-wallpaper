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
# 跟随模式切换清拖动残留：panel→文字区 时 lyrics_pos 必须被清掉
win.cfg["lyrics_pos"] = [100, 100]
win.lyr_follow_var.set("跟随壁纸文字区")
win._save()
residue_cleared = win.cfg.get("lyrics_pos") is None
# 不切换模式时残留保留（粘滞语义不破坏）
win.cfg["lyrics_pos"] = [200, 200]
win._save()
residue_kept = win.cfg.get("lyrics_pos") == [200, 200]
ok_saved = os.path.exists(config.CONFIG_PATH)

# 关键变量存在性
missing = [a for a in ("bg_style_var", "pause_shrink_pct_var", "show_text_var", "lyr_side_var",
                       "lyr_gap_var", "vis_gap_var", "_info_tpl_var") if not hasattr(win, a)]
# 数值下拉允许自由输入（readonly 已去除）
def find_combo(parent, var):
    for c in parent.winfo_children():
        if isinstance(c, ttk.Combobox) and str(c.cget("textvariable")) == str(var):
            return c
        r = find_combo(c, var)
        if r:
            return r
    return None

free_input = all(find_combo(win._pages[pn], v) is not None
                 and find_combo(win._pages[pn], v).cget("state") != "readonly"
                 for pn, v in (("面板", win.vis_w_var), ("面板", win.vis_h_var),
                               ("面板", win.lyr_w_var), ("封面", win.cover_margin_var)))
print("pages:", list(win._pages.keys()))
print("save_ok:", ok_saved, "residue_cleared:", residue_cleared, "residue_kept:", residue_kept,
      "free_input:", free_input, "missing_vars:", missing)
print("shots:", len(shots))
for p in shots:
    print("  ", p)
ok = ok_saved and residue_cleared and residue_kept and free_input and not missing
print("RESULT:", "ALL_PASS" if ok else "FAILED")
toplevel.destroy()
root.destroy()
