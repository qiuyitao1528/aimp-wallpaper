"""桌面层钉窗共用逻辑（音乐卡片 / 可视化面板共用）。

Progman/WorkerW 技巧 + Win11 26xxx 适配（窗口需 WS_EX_LAYERED，微软官方建议，
见 lively issue #2074）；失败自动降级：双 WorkerW 查找 → SetParent(Progman)。
"""
from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_int, c_size_t, c_ssize_t, c_void_p
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

HWND_T = c_void_p
WPARAM_T = c_size_t
LPARAM_T = c_ssize_t
LRESULT_T = c_ssize_t

user32.FindWindowW.restype = HWND_T
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = HWND_T
user32.FindWindowExW.argtypes = [HWND_T, HWND_T, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SetParent.restype = HWND_T
user32.SetParent.argtypes = [HWND_T, HWND_T]
user32.GetAncestor.restype = HWND_T
user32.GetAncestor.argtypes = [HWND_T, wintypes.UINT]
user32.GetParent.restype = HWND_T
user32.GetParent.argtypes = [HWND_T]
user32.GetWindowRect.argtypes = [HWND_T, POINTER(wintypes.RECT)]
user32.MoveWindow.restype = wintypes.BOOL
user32.MoveWindow.argtypes = [HWND_T, c_int, c_int, c_int, c_int, wintypes.BOOL]
user32.GetWindowLongPtrW.restype = c_ssize_t
user32.GetWindowLongPtrW.argtypes = [HWND_T, c_int]
user32.SetWindowLongPtrW.restype = c_ssize_t
user32.SetWindowLongPtrW.argtypes = [HWND_T, c_int, c_ssize_t]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.SetLayeredWindowAttributes.argtypes = [HWND_T, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD]
user32.SendMessageTimeoutW.restype = c_size_t
user32.SendMessageTimeoutW.argtypes = [HWND_T, wintypes.UINT, WPARAM_T, LPARAM_T,
                                       wintypes.UINT, wintypes.UINT, POINTER(c_size_t)]
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND_T, LPARAM_T)
user32.EnumWindows.argtypes = [ENUMPROC, LPARAM_T]
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, c_void_p, wintypes.UINT]

GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY, LWA_ALPHA = 1, 2
SMTO_ABORTIFHUNG = 2
SPI_GETWORKAREA = 0x0030
MSG_052C = 0x052C

# 颜色键：卡片外角用此颜色的像素在分层窗口中变透明+可穿透
KEY = (1, 2, 3)
KEY_HEX = "#010203"


def find_desktop_parent() -> HWND_T | None:
    """返回应 SetParent 的目标：双 WorkerW 查找 → Progman 兜底。"""
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return None
    dummy = c_size_t()
    user32.SendMessageTimeoutW(progman, MSG_052C, 0, 0, SMTO_ABORTIFHUNG, 1000, byref(dummy))
    found: list[int] = []

    def on_window(hwnd, _lp):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            found.append(hwnd)
            return False  # 找到即停
        return True

    user32.EnumWindows(ENUMPROC(on_window), 0)
    target = None
    if found:
        nxt = user32.FindWindowExW(None, HWND_T(found[0]), "WorkerW", None)
        if nxt:
            target = nxt
    if not target:
        # 某些 Win11 版本需要 0xD,1 变体才会生成第二个 WorkerW
        user32.SendMessageTimeoutW(progman, MSG_052C, 0xD, 1, SMTO_ABORTIFHUNG, 1000, byref(dummy))
        found.clear()
        user32.EnumWindows(ENUMPROC(on_window), 0)
        if found:
            nxt = user32.FindWindowExW(None, HWND_T(found[-1]), "WorkerW", None)
            if nxt:
                target = nxt
    return target if target else progman  # 兜底：直接挂 Progman


def style_desktop_widget(hwnd, alpha: int) -> None:
    """TOOLWINDOW + NOACTIVATE + LAYERED（色键透明 + 整窗 alpha）。"""
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
    user32.SetLayeredWindowAttributes(hwnd, (KEY[0] | KEY[1] << 8 | KEY[2] << 16), int(alpha),
                                     LWA_COLORKEY | LWA_ALPHA)


def pin_to_desktop(hwnd, want_x: int, want_y: int, w: int, h: int) -> bool:
    """把窗口钉到桌面层并移动到屏幕坐标 (want_x, want_y)。返回是否成功。"""
    parent = find_desktop_parent()
    if not parent:
        return False
    user32.SetParent(HWND_T(hwnd), parent)
    pr = wintypes.RECT()
    user32.GetWindowRect(parent, byref(pr))
    user32.MoveWindow(HWND_T(hwnd), want_x - pr.left, want_y - pr.top, w, h, True)
    return True


def work_area() -> tuple[int, int, int, int]:
    """主屏工作区 (left, top, right, bottom)。"""
    wa = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, byref(wa), 0)
    return wa.left, wa.top, wa.right, wa.bottom
