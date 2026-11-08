# -*- coding: utf-8 -*-
"""测试：把 AIMP 可视化窗口 SetParent 到桌面层右下角，验证能否正常渲染；然后还原。"""
import ctypes
import subprocess
import sys
import time
from ctypes import POINTER, byref, c_size_t, c_ssize_t, c_void_p
from ctypes import wintypes

user32 = ctypes.windll.user32

HWND_T = c_void_p
user32.FindWindowW.restype = HWND_T
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = HWND_T
user32.FindWindowExW.argtypes = [HWND_T, HWND_T, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SetParent.restype = HWND_T
user32.SetParent.argtypes = [HWND_T, HWND_T]
user32.GetParent.restype = HWND_T
user32.GetParent.argtypes = [HWND_T]
user32.MoveWindow.restype = wintypes.BOOL
user32.MoveWindow.argtypes = [HWND_T, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
user32.GetWindowRect.argtypes = [HWND_T, POINTER(wintypes.RECT)]
user32.ShowWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [HWND_T, ctypes.c_int]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [HWND_T]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [HWND_T, HWND_T, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetWindowLongPtrW.restype = c_ssize_t
user32.GetWindowLongPtrW.argtypes = [HWND_T, ctypes.c_int]
user32.SetWindowLongPtrW.pin = None
user32.SetWindowLongPtrW.restype = c_ssize_t
user32.SetWindowLongPtrW.argtypes = [HWND_T, ctypes.c_int, c_ssize_t]
user32.SendMessageTimeoutW.restype = c_size_t
user32.SendMessageTimeoutW.argtypes = [HWND_T, wintypes.UINT, c_size_t, c_ssize_t,
                                       wintypes.UINT, wintypes.UINT, POINTER(c_size_t)]
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND_T, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUMPROC, wintypes.LPARAM]
user32.GetAncestor.restype = HWND_T
user32.GetAncestor.argtypes = [HWND_T, wintypes.UINT]

GA_ROOT, GWL_EXSTYLE, WS_EX_TOOLWINDOW = 2, -20, 0x80
SMTO_ABORTIFHUNG = 2
MSG_052C = 0x052C
SW_SHOWNA, SW_HIDE = 8, 0
SWP_NOACTIVATE, SWP_NOZORDER, SWP_NOSIZE = 0x10, 0x4, 0x1


def find_desktop_parent():
    progman = user32.FindWindowW("Progman", None)
    dummy = c_size_t()
    user32.SendMessageTimeoutW(progman, MSG_052C, 0, 0, SMTO_ABORTIFHUNG, 1000, byref(dummy))

    def on_w(hwnd, _lp):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            found.append(hwnd)
            return False
        return True

    found = []
    user32.EnumWindows(ENUMPROC(on_w), 0)
    target = None
    if found:
        target = user32.FindWindowExW(None, HWND_T(found[0]), "WorkerW", None)
    if not target:
        user32.SendMessageTimeoutW(progman, MSG_052C, 0xD, 1, SMTO_ABORTIFHUNG, 1000, byref(dummy))
        found = []

        def on_w2(hwnd, _lp):
            if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(ENUMPROC(on_w2), 0)
        if found:
            target = user32.FindWindowExW(None, HWND_T(found[-1]), "WorkerW", None)
    return target or progman


parent = find_desktop_parent()
vis = user32.FindWindowExW(None, None, "TASEScene", "可视化")
print(f"桌面层目标 = {parent:#x}  可视化窗口 = {vis:#x} 可见={bool(user32.IsWindowVisible(vis))}")

orig = wintypes.RECT()
user32.GetWindowRect(vis, byref(orig))
orig_parent = user32.GetParent(vis)
ex_orig = user32.GetWindowLongPtrW(vis, GWL_EXSTYLE)
pr = wintypes.RECT()
user32.GetWindowRect(parent, byref(pr))

W, H = 480, 336  # 648x453 的 0.74
x = pr.right - W - 40
y = pr.bottom - H - 20

user32.SetWindowLongPtrW(vis, GWL_EXSTYLE, ex_orig | WS_EX_TOOLWINDOW)
user32.SetParent(HWND_T(vis), HWND_T(parent))
user32.MoveWindow(HWND_T(vis), x - pr.left, y - pr.top, W, H, True)
user32.ShowWindow(HWND_T(vis), SW_SHOWNA)
print(f"已钉到桌面层 ({x},{y}) {W}x{H}，等 2.5s 渲染...")
time.sleep(2.5)

# 截桌面右下角区域看效果
ps = r"""
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$b = New-Object System.Drawing.Bitmap 700, 450
$g = [System.Drawing.Graphics]::FromImage($b)
$g.CopyFromScreen({}-40, {}-360, 0, 0, (New-Object System.Drawing.Size 700, 450))
$b.Save('E:\aimp-wallpaper\scripts\vis_desktop.png')
""".format(x + W, y + H)
subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True)
print("已截图 vis_desktop.png（窗口保持钉住状态，先不还原，看看效果）")
