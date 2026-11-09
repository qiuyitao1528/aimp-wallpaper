"""设置窗口：壁纸 / 文字 / 排版 / 面板 / 系统 五个标签页。"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import colorchooser, ttk

from . import config

SIZE_CHOICES = [32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160]
GAP_CHOICES = [0, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40]
BLUR_CHOICES = [8, 16, 24, 28, 32, 40, 56, 72, 100]
OFFSET_CHOICES = [-200, -150, -100, -60, -30, 0, 30, 60, 100, 150, 200]
SCALE_CHOICES = ["0.5", "0.6", "0.7", "0.8", "0.9", "1.0", "1.1", "1.2", "1.4", "1.6"]
FPS_CHOICES = ["15", "20", "24", "30", "45", "60", "90", "120"]
ALIGN_ITEMS = [("左对齐", "left"), ("居中", "center"), ("右对齐", "right")]
VALIGN_ITEMS = [("顶部", "top"), ("居中", "center"), ("底部", "bottom")]
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
        self.win.after(1200, lambda: self.win.attributes("-topmost", False))
        self.screen_h = max(1, root.winfo_screenheight())

        self._fonts = _available_fonts()
        self._file_to_label = {f: lb for lb, f in self._fonts}
        self._default_label = "默认（微软雅黑）"

        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self._pages, self._rows = {}, {}
        for name in ("壁纸", "文字", "排版", "面板", "系统"):
            f = ttk.Frame(nb, padding=10)
            nb.add(f, text=name)
            self._pages[name] = f
            self._rows[f] = 0

        pad = dict(padx=6, pady=3)

        def add(page, label, widget):
            r = self._rows[page]
            if label:
                ttk.Label(page, text=label).grid(row=r, column=0, sticky="w", **pad)
                widget.grid(row=r, column=1, sticky="w", **pad)
            else:
                widget.grid(row=r, column=0, columnspan=2, sticky="w", **pad)
            self._rows[page] = r + 1

        def combo(page, label, values, current, width=8):
            var = tk.StringVar(value=str(current))
            vals = [str(v) for v in values]
            if str(current) not in vals:
                vals.insert(0, str(current))
            add(page, label, ttk.Combobox(page, textvariable=var, values=vals, width=width))
            return var

        def check(page, label, value):
            var = tk.BooleanVar(value=bool(value))
            add(page, None, ttk.Checkbutton(page, text=label, variable=var))
            return var

        def labeled(page, label, mapping, current):
            var = tk.StringVar(value={v: k for k, v in mapping}.get(current, mapping[0][0]))
            add(page, label, ttk.Combobox(page, textvariable=var, values=[k for k, _ in mapping],
                                           state="readonly", width=10))
            return var

        def px_of(key, ratio_default):
            return int(self.screen_h * float(cfg.get(key, ratio_default)))

        # ---------------- 壁纸 ----------------
        pg = self._pages["壁纸"]
        self.blur_var = combo(pg, "背景模糊(像素)", BLUR_CHOICES, int(cfg.get("blur_radius", 28)))
        self.cover_scale_var = combo(pg, "封面大小(倍率)", SCALE_CHOICES,
                                     cfg.get("cover_scale", 1.0) or 1.0)
        self.cover_dx_var = combo(pg, "封面 X 偏移(像素)", OFFSET_CHOICES,
                                  int(cfg.get("cover_offset_x", 0) or 0))
        self.cover_dy_var = combo(pg, "封面 Y 偏移(像素)", OFFSET_CHOICES,
                                  int(cfg.get("cover_offset_y", 0) or 0))

        # ---------------- 文字 ----------------
        pg = self._pages["文字"]
        self.title_px_var = combo(pg, "歌名字号(像素)", SIZE_CHOICES, px_of("title_size_ratio", 0.075))
        self.title_font_var = combo(pg, "歌名字体",
                                    [self._default_label] + [lb for lb, _ in self._fonts],
                                    self._file_to_label.get(cfg.get("title_font_file"), self._default_label),
                                    width=28)
        self.title_color_var = self._color_row(add, pg, "歌名颜色", "title_color", "#FFFFFF")
        self.title_of_var = labeled(pg, "歌名过长", [("换行", "wrap"), ("省略号", "ellipsis")],
                                    cfg.get("title_overflow", "wrap"))
        self.tbold_var = check(pg, "歌名加粗", cfg.get("title_bold", True))

        self.sub_px_var = combo(pg, "副行字号(像素)", SIZE_CHOICES, px_of("sub_size_ratio", 0.042))
        self.sub_font_var = combo(pg, "歌手·专辑字体",
                                  [self._default_label] + [lb for lb, _ in self._fonts],
                                  self._file_to_label.get(cfg.get("sub_font_file"), self._default_label),
                                  width=28)
        self.sub_color_var = self._color_row(add, pg, "副行颜色", "sub_color", "#FFFFFF")
        self.sub_of_var = labeled(pg, "副行过长", [("省略号", "ellipsis"), ("换行", "wrap")],
                                  cfg.get("sub_overflow", "ellipsis"))
        self.sbold_var = check(pg, "副行加粗", cfg.get("sub_bold", False))
        self.shadow_var = check(pg, "文字阴影", cfg.get("text_shadow", True))

        # ---------------- 排版 ----------------
        pg = self._pages["排版"]
        self.tsg_var = combo(pg, "标题-副行间距(像素)", GAP_CHOICES, px_of("title_sub_gap_ratio", 0.02))
        self.tlg_var = combo(pg, "标题行间距(像素)", GAP_CHOICES, px_of("title_line_gap_ratio", 0.012))
        self.slg_var = combo(pg, "副行行间距(像素)", GAP_CHOICES, px_of("sub_line_gap_ratio", 0.014))
        self.text_dx_var = combo(pg, "文字 X 偏移(像素)", OFFSET_CHOICES,
                                 int(cfg.get("text_offset_x", 0) or 0))
        self.text_dy_var = combo(pg, "文字 Y 偏移(像素)", OFFSET_CHOICES,
                                 int(cfg.get("text_offset_y", 0) or 0))
        self.text_align_var = labeled(pg, "文字水平对齐", ALIGN_ITEMS, cfg.get("text_align", "left"))
        self.text_valign_var = labeled(pg, "文字垂直对齐", VALIGN_ITEMS, cfg.get("text_valign", "center"))

        # ---------------- 面板 ----------------
        pg = self._pages["面板"]
        self.fps_var = combo(pg, "刷新率(FPS)", FPS_CHOICES, int(cfg.get("vis_fps", 30) or 30))
        self.lock_var = check(pg, "锁定频谱面板（禁拖动，仍跟随壁纸）", cfg.get("vis_locked"))

        # ---------------- 系统 ----------------
        pg = self._pages["系统"]
        self.autostart_var = check(pg, "开机自启动", autostart_enabled())
        self.restore_var = check(pg, "退出时恢复原壁纸", cfg.get("restore_on_quit", True))

        ttk.Button(self.win, text="保存", command=self._save).pack(pady=8)
        self.status = ttk.Label(self.win, text="保存后壁纸立即重新渲染", foreground="#888888")
        self.status.pack(pady=(0, 8))

        # transient 只能绑到"可见"父窗：主窗隐藏时绑上去会让设置窗一起不显示
        if root.winfo_viewable():
            self.win.transient(root)
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except Exception:
            pass

    def _color_row(self, add, page, label, key, default):
        var = tk.StringVar(value=str(self.cfg.get(key, default) or default).upper())

        def pick():
            _rgb, hexv = colorchooser.askcolor(color=var.get(), parent=self.win, title=label)
            if hexv:
                var.set(str(hexv).upper())
                btn.configure(bg=var.get(), fg="#000000" if _luma(var.get()) > 140 else "#FFFFFF")

        btn = tk.Button(page, textvariable=var, bg=var.get(), relief="groove", width=10, command=pick)
        add(page, label, btn)
        return var

    def _int(self, var, key, lo, hi, ratio=False):
        try:
            v = int(str(var.get()).strip())
        except (TypeError, ValueError):
            return
        self.cfg[key] = max(lo, min(v, hi)) / self.screen_h if ratio else max(lo, min(v, hi))

    def _float(self, var, key, lo, hi):
        try:
            v = float(str(var.get()).strip())
        except (TypeError, ValueError):
            return
        self.cfg[key] = max(lo, min(v, hi))

    def _save(self):
        self._int(self.blur_var, "blur_radius", 4, 200)
        self._float(self.cover_scale_var, "cover_scale", 0.3, 2.0)
        self._int(self.cover_dx_var, "cover_offset_x", -2000, 2000)
        self._int(self.cover_dy_var, "cover_offset_y", -2000, 2000)
        self._int(self.title_px_var, "title_size_ratio", 12, self.screen_h, ratio=True)
        self._int(self.sub_px_var, "sub_size_ratio", 10, self.screen_h, ratio=True)
        self._int(self.tsg_var, "title_sub_gap_ratio", 0, 300, ratio=True)
        self._int(self.tlg_var, "title_line_gap_ratio", 0, 300, ratio=True)
        self._int(self.slg_var, "sub_line_gap_ratio", 0, 300, ratio=True)
        self._int(self.text_dx_var, "text_offset_x", -2000, 2000)
        self._int(self.text_dy_var, "text_offset_y", -2000, 2000)
        self._int(self.fps_var, "vis_fps", 10, 120)

        label_to_file = {lb: f for lb, f in self._fonts}
        label_to_file[self._default_label] = None
        self.cfg["title_font_file"] = label_to_file.get(self.title_font_var.get())
        self.cfg["sub_font_file"] = label_to_file.get(self.sub_font_var.get())
        self.cfg["title_color"] = self.title_color_var.get()
        self.cfg["sub_color"] = self.sub_color_var.get()
        self.cfg["title_bold"] = self.tbold_var.get()
        self.cfg["sub_bold"] = self.sbold_var.get()
        self.cfg["text_shadow"] = self.shadow_var.get()
        self.cfg["title_overflow"] = dict([("换行", "wrap"), ("省略号", "ellipsis")]).get(
            self.title_of_var.get(), "wrap")
        self.cfg["sub_overflow"] = dict([("换行", "wrap"), ("省略号", "ellipsis")]).get(
            self.sub_of_var.get(), "ellipsis")
        self.cfg["text_align"] = dict(ALIGN_ITEMS).get(self.text_align_var.get(), "left")
        self.cfg["text_valign"] = dict(VALIGN_ITEMS).get(self.text_valign_var.get(), "center")
        self.cfg["vis_locked"] = self.lock_var.get()
        self.cfg["restore_on_quit"] = self.restore_var.get()
        config.save(self.cfg)

        if not set_autostart(self.autostart_var.get()):
            self.status.config(text="自启动设置写入失败", foreground="#C0392B")
        else:
            self.status.config(text="已保存，壁纸正在重新渲染", foreground="#2E7D32")
