# -*- coding: utf-8 -*-
"""对比实验：同一内容，窗口A=纯alpha分层（无色键），窗口B=色键分层。各截一张。"""
import sys
import tkinter as tk

sys.path.insert(0, r"E:\aimp-wallpaper")
from PIL import Image, ImageDraw, ImageTk
from aimp_wallpaper import desktop

root = tk.Tk()
root.overrideredirect(True)

results = {}


def make_window(x, y, colorkey: bool):
    w = tk.Toplevel(root)
    w.overrideredirect(True)
    W, H = 300, 120
    c = tk.Canvas(w, width=W, height=H, bg="#181A22" if not colorkey else desktop.KEY_HEX,
                  highlightthickness=0, bd=0)
    c.pack()
    if colorkey:
        img = Image.new("RGB", (W, H), desktop.KEY)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, fill=(24, 26, 34))
        d.text((30, 50), "B 色键窗口", fill=(242, 244, 248))
        pi = ImageTk.PhotoImage(img)
        c.create_image(0, 0, image=pi, anchor="nw")
        results[("img", colorkey)] = pi
    c.create_rectangle(20, 80, 60, 100, fill="#FF3344", outline="")
    c.create_text(100, 90, text=("A 纯alpha" if not colorkey else "B 色键"), fill="#FFFFFF", anchor="w")
    w.geometry(f"+{x}+{y}")
    w.update_idletasks()
    w.update()
    hwnd = desktop.user32.GetAncestor(desktop.HWND_T(w.winfo_id()), desktop.GA_ROOT)
    if colorkey:
        desktop.style_desktop_widget(hwnd, 235)  # 色键+alpha
    else:
        ex = desktop.user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE)
        desktop.user32.SetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE,
                                         ex | desktop.WS_EX_LAYERED | desktop.WS_EX_TOOLWINDOW)
        desktop.user32.SetLayeredWindowAttributes(hwnd, 0, 235, desktop.LWA_ALPHA)
    desktop.pin_to_desktop(hwnd, x, y, W, H)
    return w, hwnd


wa = make_window(700, 700, False)
wb = make_window(700, 850, True)
root.after(4000, root.destroy)
root.mainloop()
print("对比窗口已退出")
