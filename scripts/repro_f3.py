# -*- coding: utf-8 -*-
"""F3：顶层窗口 + SetWindowPos(Progman 插到我们下面) 实现桌面级 z-order。"""
import sys
import tkinter as tk

sys.path.insert(0, r"E:\aimp-wallpaper")
from ctypes import byref, c_void_p
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageTk
from aimp_wallpaper import desktop

user32 = desktop.user32
HWND_TOP = 0
SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE = 0x2, 0x1, 0x10

root = tk.Tk()
root.overrideredirect(True)
root.geometry("+3000+3000")

w = tk.Toplevel(root)
w.overrideredirect(True)
W, H = 300, 120
c = tk.Canvas(w, width=W, height=H, bg=desktop.KEY_HEX, highlightthickness=0, bd=0)
c.pack()
img = Image.new("RGB", (W, H), desktop.KEY)
d = ImageDraw.Draw(img)
d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, fill=(24, 26, 34))
d.rectangle([20, 40, 280, 80], fill="#FF3344")
d.text((30, 15), "F3: z-order desktop widget", fill=(255, 255, 255))
pi = ImageTk.PhotoImage(img)
c.create_image(0, 0, image=pi, anchor="nw")
w.geometry("+700+700")
w.update_idletasks()
w.update()
hwnd = user32.GetAncestor(desktop.HWND_T(w.winfo_id()), desktop.GA_ROOT)
desktop.style_desktop_widget(hwnd, 235)  # TOOLWINDOW+NOACTIVATE+色键分层


def push_below_desktop():
    """把 Progman 压到我们窗口之下（我们=桌面级 z-order 底部，仍在所有普通窗口之下）。"""
    progman = user32.FindWindowW("Progman", None)
    if progman:
        user32.SetWindowPos(c_void_p(hwnd), c_void_p(progman), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


push_below_desktop()
root.after(500, push_below_desktop)  # 周期强化

root.after(4000, root.destroy)
root.mainloop()
print("done")
