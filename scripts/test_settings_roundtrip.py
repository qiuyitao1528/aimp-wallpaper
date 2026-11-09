# -*- coding: utf-8 -*-
"""设置项全量往返测试：每项改成新值 → 保存 → 重新读取 → 核对。
先备份真实 config，测完原样还原。"""
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"E:\aimp-wallpaper")

import tkinter as tk

from aimp_wallpaper import config, settings_gui as sg

REAL = config.CONFIG_PATH
BACKUP = REAL + ".bak-test"
shutil.copyfile(REAL, BACKUP)
tmp = tempfile.mkdtemp()
sg.startup_lnk_path = lambda: os.path.join(tmp, "AIMP Wallpaper.lnk")  # 沙箱，不碰真实启动项

failures = []
try:
    cfg = config.load()
    root = tk.Tk()
    root.withdraw()
    root.update()
    sw = sg.SettingsWindow(root, cfg)

    # 逐项设成"与当前不同"的值
    sw.title_px_var.set("96")
    sw.sub_px_var.set("52")
    sw.tlg_var.set("16")
    sw.tsg_var.set("28")
    sw.slg_var.set("20")
    sw.blur_var.set("40")
    sw.fps_var.set("60")
    simhei = [lb for lb, f in sw._fonts if f == "simhei.ttf"]
    if simhei:
        sw.title_font_var.set(simhei[0])
    sw.title_color_var.set("#FF8000")
    sw.sub_color_var.set("#00FF80")
    sw.title_of_var.set("省略号")
    sw.sub_of_var.set("换行")
    sw.shadow_var.set(False)
    sw.tbold_var.set(False)
    sw.sbold_var.set(True)
    sw.lock_var.set(True)
    sw.restore_var.set(False)
    sw.autostart_var.set(True)
    sw._save()
    print("状态栏:", sw.status.cget("text"))

    saved = json.load(io.open(config.CONFIG_PATH, encoding="utf-8"))
    screen_h = sw.screen_h
    checks = [
        ("title_size_ratio", round(96 / screen_h, 6)),
        ("sub_size_ratio", round(52 / screen_h, 6)),
        ("title_line_gap_ratio", round(16 / screen_h, 6)),
        ("title_sub_gap_ratio", round(28 / screen_h, 6)),
        ("sub_line_gap_ratio", round(20 / screen_h, 6)),
        ("blur_radius", 40),
        ("vis_fps", 60),
        ("title_color", "#FF8000"),
        ("sub_color", "#00FF80"),
        ("title_overflow", "ellipsis"),
        ("sub_overflow", "wrap"),
        ("text_shadow", False),
        ("title_bold", False),
        ("sub_bold", True),
        ("vis_locked", True),
        ("restore_on_quit", False),
    ]
    for key, want in checks:
        got = saved.get(key)
        okv = (abs(got - want) < 1e-6) if isinstance(want, float) else (got == want)
        print(("  OK  " if okv else "  FAIL") + f" {key}: {got!r} (期望 {want!r})")
        if not okv:
            failures.append(key)

    # 往返：重新 load 再建窗口，控件应回显保存值
    cfg2 = config.load()
    sw2 = sg.SettingsWindow(root, cfg2)
    print("重开后回显: 字号", sw2.title_px_var.get(), "| FPS", sw2.fps_var.get(),
          "| 颜色", sw2.title_color_var.get(), "| 过长", sw2.title_of_var.get())
    if sw2.fps_var.get() != "60":
        failures.append("fps 回显")
    if sw2.title_of_var.get() != "省略号":
        failures.append("过长回显")
    root.destroy()
finally:
    shutil.copyfile(BACKUP, REAL)
    os.remove(BACKUP)
    print("已还原真实 config")

print("=== 结果:", "全部通过" if not failures else f"失败项 {failures}", "===")
