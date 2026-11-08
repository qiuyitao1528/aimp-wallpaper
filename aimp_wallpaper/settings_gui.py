"""设置窗口：壁纸 / 频谱 / 控件 / 系统 四页。"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import colorchooser, ttk

from . import config, desktop, wallpaper

SIZE_CHOICES = [32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160]
GAP_CHOICES = [0, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40]
BLUR_CHOICES = [8, 16, 24, 32, 40, 56, 72, 100]
ALPHA_CHOICES = [120, 140, 160, 180, 200, 220, 232, 255]
FPS_CHOICES = ["15", "20", "24", "30", "45", "60", "90", "120"]
BG_CHOICES = [("高斯模糊", "blur"), ("模糊+暗角", "blur_vignette"),
              ("原图铺满", "sharp"), ("主色渐变", "gradient")]
FONTS_FALLBACK = [
    ("微软雅黑（默认）", "msyhbd.ttc"), ("微软雅黑 常规", "msyh.ttc"), ("微软雅黑 Light", "msyhl.ttc"),
    ("黑体", "simhei.ttf"), ("宋体", "simsun.ttc"), ("楷体", "simkai.ttf"),
    ("仿宋", "simfang.ttf"), ("等线", "Deng.ttf"), ("等线 Light", "DengL.ttf"),
    ("Segoe UI", "segoeui.ttf"),
]


def startup_lnk_path() -> str:
    return os.path.join(
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
        "AIMP Wallpaper.lnk")


def autostart_enabled() -> bool:
    return os.path.exists(startup_lnk_path())


def set_autostart(enabled: bool) -> bool:
    lnk = startup_lnk_path()
    try:
        if enabled:
            if getattr(sys, "frozen", False):
                target, args, wd = sys.executable, "", os.path.dirname(sys.executable)
            else:
                proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                pyw = os.path.join(proj, ".venv", "Scripts", "pythonw.exe")
                if not os.path.exists(pyw):
                    pyw = sys.executable.replace("python.exe", "pythonw.exe")
                target, args, wd = pyw, "-m aimp_wallpaper", proj
            ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{}');"
                  "$s.TargetPath='{}';$s.Arguments='{}';$s.WorkingDirectory='{}';$s.Save()").format(
                      lnk.replace("'", "''"), target.replace("'", "''"),
                      args.replace("'", "''"), wd.replace("'", "''"))
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=20)
            return os.path.exists(lnk)
        if os.path.exists(lnk):
            os.remove(lnk)
        return True
    except Exception:
        return False


def _luma(hex_color: str) -> int:
    """'#RRGGBB' 亮度（0~255），用于色块按钮上黑/白字的选择。"""
    try:
        s = hex_color.lstrip("#")
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return (r * 299 + g * 587 + b * 114) // 1000
    except (ValueError, IndexError):
        return 0


def _available_fonts() -> list[tuple[str, str]]:
    from . import wallpaper
    fonts = wallpaper.font_entries()
    if fonts:
        return fonts
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return sorted((lb, f) for lb, f in FONTS_FALLBACK if os.path.exists(os.path.join(fonts_dir, f)))


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.cfg = cfg
        self.win = tk.Toplevel(root)
        self.win.title("AIMP Wallpaper 设置")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.after(1000, lambda: self.win.attributes("-topmost", False))
        self.screen_h = max(1, root.winfo_screenheight())

        self._fonts = _available_fonts()
        self._file_to_label = {f: lb for lb, f in self._fonts}
        self._default_label = "默认（微软雅黑）"

        pad = dict(padx=8, pady=3)
        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self._pages = {}
        self._rows = {}
        for name in ("壁纸", "频谱", "控件", "系统"):
            f = ttk.Frame(nb, padding=10)
            nb.add(f, text=name)
            self._pages[name] = f
            self._rows[f] = 0

        def add(page, label_text, widget, span=2):
            if label_text:
                ttk.Label(page, text=label_text).grid(row=self._rows[page], column=0,
                                                      sticky="w", **pad)
                widget.grid(row=self._rows[page], column=1, sticky="w", **pad)
            else:
                widget.grid(row=self._rows[page], column=0, columnspan=span, sticky="w", **pad)
            self._rows[page] += 1

        def px_combo(page, label_text, key, ratio_default, choices, lo, hi):
            cur = int(self.screen_h * float(cfg.get(key, ratio_default)))
            values = [str(x) for x in choices]
            if str(cur) not in values:
                values.insert(0, str(cur))
            var = tk.StringVar(value=str(cur))
            add(page, label_text, ttk.Combobox(page, textvariable=var, values=values, width=8))
            return var, lo, hi

        # ================= 壁纸 =================
        pg = self._pages["壁纸"]
        bg_key2label = {k: lb for lb, k in BG_CHOICES}
        self.bg_style_var = tk.StringVar(
            value=bg_key2label.get(cfg.get("bg_style", "blur"), "高斯模糊"))
        add(pg, "背景方案", ttk.Combobox(pg, textvariable=self.bg_style_var, width=12,
                                         values=[lb for lb, _ in BG_CHOICES], state="readonly"))
        blur_cur = int(cfg.get("blur_radius", 28))
        blur_values = [str(x) for x in BLUR_CHOICES]
        if str(blur_cur) not in blur_values:
            blur_values.insert(0, str(blur_cur))
        self.blur_var = tk.StringVar(value=str(blur_cur))
        add(pg, "模糊半径(像素)", ttk.Combobox(pg, textvariable=self.blur_var,
                                               values=blur_values, width=8))

        def font_row(label_text, key):
            var = tk.StringVar(value=self._file_to_label.get(cfg.get(key), self._default_label))
            add(pg, label_text, ttk.Combobox(pg, textvariable=var, width=30,
                                             values=[self._default_label] + [lb for lb, _ in self._fonts],
                                             state="readonly"))
            return var

        self.title_px_var, self._t_lo, self._t_hi = px_combo(
            pg, "歌名字号(像素)", "title_size_ratio", 0.075, SIZE_CHOICES, 16, self.screen_h // 2)
        self.title_font_var = font_row("歌名字体", "title_font_file")
        self.title_of_var = self._overflow_row(add, pg, "歌名过长", "title_overflow", "wrap")
        self.title_color_var = self._color_row(add, pg, "歌名颜色", "title_color", "#FFFFFF")
        self.tbold_var = tk.BooleanVar(value=bool(cfg.get("title_bold", True)))
        add(pg, "歌名加粗", ttk.Checkbutton(pg, text="加粗", variable=self.tbold_var))
        self.tlg_var, self._tlg_lo, self._tlg_hi = px_combo(
            pg, "标题行间距", "title_line_gap_ratio", 0.012, GAP_CHOICES, 0, 200)
        self.tsg_var, self._tsg_lo, self._tsg_hi = px_combo(
            pg, "标题-副行间距", "title_sub_gap_ratio", 0.02, GAP_CHOICES, 0, 200)
        self.sub_px_var, self._s_lo, self._s_hi = px_combo(
            pg, "副行字号(像素)", "sub_size_ratio", 0.042, SIZE_CHOICES, 12, self.screen_h // 2)
        self.sub_font_var = font_row("歌手·专辑字体", "sub_font_file")
        self.sub_of_var = self._overflow_row(add, pg, "副行过长", "sub_overflow", "ellipsis")
        self.sub_color_var = self._color_row(add, pg, "副行颜色", "sub_color", "#FFFFFF")
        self.sbold_var = tk.BooleanVar(value=bool(cfg.get("sub_bold", False)))
        add(pg, "副行加粗", ttk.Checkbutton(pg, text="加粗", variable=self.sbold_var))
        self.slg_var, self._slg_lo, self._slg_hi = px_combo(
            pg, "副行行间距", "sub_line_gap_ratio", 0.014, GAP_CHOICES, 0, 200)
        self.shadow_var = tk.BooleanVar(value=bool(cfg.get("text_shadow", True)))
        add(pg, "文字阴影", ttk.Checkbutton(pg, text="阴影", variable=self.shadow_var))

        # ================= 频谱 =================
        pg = self._pages["频谱"]
        self.fps_var = tk.StringVar(value=str(int(cfg.get("vis_fps", 30) or 30)))
        add(pg, "刷新率(FPS)", ttk.Combobox(pg, textvariable=self.fps_var, width=8, values=FPS_CHOICES))
        self.lock_var = tk.BooleanVar(value=bool(cfg.get("vis_locked")))
        add(pg, None, ttk.Checkbutton(pg, text="锁定频谱面板（禁拖动，仍跟随壁纸）", variable=self.lock_var))

        # ================= 控件 =================
        pg = self._pages["控件"]
        self.widget_var = tk.BooleanVar(value=not bool(cfg.get("widget_hidden")))
        add(pg, None, ttk.Checkbutton(pg, text="显示桌面音乐控件", variable=self.widget_var))
        walpha = max(60, min(255, int(cfg.get("widget_alpha", 232))))
        walpha_values = [str(x) for x in ALPHA_CHOICES]
        if str(walpha) not in walpha_values:
            walpha_values.insert(0, str(walpha))
        self.walpha_var = tk.StringVar(value=str(walpha))
        add(pg, "控件不透明度", ttk.Combobox(pg, textvariable=self.walpha_var,
                                             values=walpha_values, width=8))

        # ================= 系统 =================
        pg = self._pages["系统"]
        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        add(pg, None, ttk.Checkbutton(pg, text="开机自启动", variable=self.autostart_var))
        self.restore_var = tk.BooleanVar(value=bool(cfg.get("restore_on_quit", True)))
        add(pg, None, ttk.Checkbutton(pg, text="退出时恢复原壁纸", variable=self.restore_var))

        ttk.Button(self.win, text="保存", command=self._save).pack(pady=8)
        self.status = ttk.Label(self.win, text="保存后壁纸立即重新渲染", foreground="#888888")
        self.status.pack(pady=(0, 8))

        self.win.transient(root)

    def _overflow_row(self, add, page, label_text, key, default):
        cur = cfg_get(self.cfg, key, default)
        var = tk.StringVar(value="换行" if cur == "wrap" else "省略号")
        add(page, label_text, ttk.Combobox(page, textvariable=var, values=["换行", "省略号"],
                                           state="readonly", width=8))
        return var

    def _color_row(self, add, page, label_text, key, default):
        var = tk.StringVar(value=str(cfg_get(self.cfg, key, default) or default).upper())

        def pick():
            rgb, hexv = colorchooser.askcolor(color=var.get(), parent=self.win, title=label_text)
            if hexv:  # 取消则不改动
                var.set(str(hexv).upper())
                btn.configure(bg=var.get(), fg="#000000" if _luma(var.get()) > 140 else "#FFFFFF")

        btn = tk.Button(page, textvariable=var, bg=var.get(), relief="groove", width=10, command=pick)
        add(page, label_text, btn)
        return var

    def _save(self):
        label2key = dict(BG_CHOICES)
        self.cfg["bg_style"] = label2key.get(self.bg_style_var.get(), "blur")

        def int_val(var, key, lo, hi, per_screen_h=False):
            try:
                v = int(str(var.get()).strip())
            except ValueError:
                return  # 非法输入保留原值
            if per_screen_h:
                self.cfg[key] = max(lo, min(v, hi)) / self.screen_h
            else:
                self.cfg[key] = max(lo, min(v, hi))

        int_val(self.blur_var, "blur_radius", 4, 200)
        int_val(self.title_px_var, "title_size_ratio", 16, self.screen_h // 2, per_screen_h=True)
        int_val(self.sub_px_var, "sub_size_ratio", 12, self.screen_h // 2, per_screen_h=True)
        int_val(self.tlg_var, "title_line_gap_ratio", 0, 200, per_screen_h=True)
        int_val(self.tsg_var, "title_sub_gap_ratio", 0, 200, per_screen_h=True)
        int_val(self.slg_var, "sub_line_gap_ratio", 0, 200, per_screen_h=True)
        int_val(self.fps_var, "vis_fps", 10, 120)
        int_val(self.walpha_var, "widget_alpha", 60, 255)
        label_to_file = {lb: f for lb, f in self._fonts}
        label_to_file[self._default_label] = None
        self.cfg["title_font_file"] = label_to_file.get(self.title_font_var.get())
        self.cfg["sub_font_file"] = label_to_file.get(self.sub_font_var.get())
        self.cfg["title_overflow"] = "wrap" if self.title_of_var.get() == "换行" else "ellipsis"
        self.cfg["sub_overflow"] = "wrap" if self.sub_of_var.get() == "换行" else "ellipsis"
        self.cfg["title_color"] = self.title_color_var.get()
        self.cfg["sub_color"] = self.sub_color_var.get()
        self.cfg["text_shadow"] = self.shadow_var.get()
        self.cfg["title_bold"] = self.tbold_var.get()
        self.cfg["sub_bold"] = self.sbold_var.get()
        self.cfg["vis_locked"] = self.lock_var.get()
        self.cfg["widget_hidden"] = not self.widget_var.get()
        self.cfg["restore_on_quit"] = self.restore_var.get()
        config.save(self.cfg)
        if set_autostart(self.autostart_var.get()) != self.autostart_var.get():
            self.status.config(text="自启动设置写入失败", foreground="#C0392B")
        else:
            self.status.config(text="已保存，壁纸立即重新渲染", foreground="#2E7D32")


def cfg_get(cfg: dict, key: str, default):
    """cfg 取值，None 视为未设置（font_file 类键 None=默认）。"""
    v = cfg.get(key, default)
    return default if v is None and key.endswith("font_file") else v
