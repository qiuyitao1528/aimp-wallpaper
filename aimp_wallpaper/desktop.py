"""桌面层钉窗共用逻辑（音乐卡片 / 可视化面板共用）。

Progman/WorkerW 技巧 + Win11 26xxx 适配（窗口需 WS_EX_LAYERED，微软官方建议，
见 lively issue #2074）；失败自动降级：双 WorkerW 查找 → SetParent(Progman)。
"""
from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_int, c_size_t, c_ssize_t, c_void_p
from ctypes import wintypes

import numpy as np

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

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", wintypes.BYTE), ("BlendFlags", wintypes.BYTE),
                ("SourceConstantAlpha", wintypes.BYTE), ("AlphaFormat", wintypes.BYTE)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, POINTER(BITMAPINFO), wintypes.UINT,
                                   POINTER(c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC,
                                       POINTER(wintypes.POINT), POINTER(SIZE),
                                       wintypes.HDC, POINTER(wintypes.POINT),
                                       wintypes.COLORREF, POINTER(BLENDFUNCTION),
                                       wintypes.DWORD]

ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01


GA_ROOT = 2
GW_HWNDPREV = 3
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


def style_overlay_window(hwnd) -> None:
    """TOOLWINDOW + NOACTIVATE + LAYERED（配合 UpdateLayeredWindow 逐像素 alpha）。
    注意：不要再对该窗口调 SetLayeredWindowAttributes，二者互斥（后调者生效）。"""
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)


def set_colorkey_attr(hwnd) -> None:
    """切回色键分层模式（ULW 回退画布渲染时用）。"""
    user32.SetLayeredWindowAttributes(hwnd, (KEY[0] | KEY[1] << 8 | KEY[2] << 16), 255,
                                      LWA_COLORKEY | LWA_ALPHA)


class OverlaySurface:
    """UpdateLayeredWindow 表面：32bpp BGRA DIB（numpy 直写）+ 一帧一次原子呈现。
    update() 接收 PIL RGBA 图（straight alpha），内部预乘后上屏。"""

    def __init__(self, hwnd: int, w: int, h: int):
        self.hwnd, self.w, self.h = hwnd, int(w), int(h)
        self.hdc_screen = user32.GetDC(None)
        self.hdc = gdi32.CreateCompatibleDC(self.hdc_screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self.w
        bmi.bmiHeader.biHeight = -self.h  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        self.bits = c_void_p()
        self.hbm = gdi32.CreateDIBSection(self.hdc, byref(bmi), 0, byref(self.bits), None, 0)
        gdi32.SelectObject(self.hdc, self.hbm)
        n = self.w * self.h * 4
        self._buf = (ctypes.c_ubyte * n).from_address(self.bits.value or 0)
        self.arr = np.ctypeslib.as_array(self._buf).reshape(self.h, self.w, 4)
        self.blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        self.ok = bool(self.hbm) and bool(self.bits.value)

    def update(self, img, pos: tuple[int, int] | None = None) -> bool:
        """PIL RGBA（straight alpha）→ 预乘 BGRA → ULW 原子呈现。返回是否成功。
        pos=(x, y) 时显式指定屏幕位置（推荐：规避 Tk 窗口实际尺寸与表面不一致的坑）。"""
        if not self.ok:
            return False
        a = np.asarray(img)
        alpha = a[..., 3:4].astype(np.uint16)
        self.arr[..., 0] = a[..., 2] * alpha[..., 0] // 255  # B
        self.arr[..., 1] = a[..., 1] * alpha[..., 0] // 255  # G
        self.arr[..., 2] = a[..., 0] * alpha[..., 0] // 255  # R
        self.arr[..., 3] = a[..., 3]
        if pos:
            pt_dst = wintypes.POINT(*pos)
            size = SIZE(self.w, self.h)
            return bool(user32.UpdateLayeredWindow(
                HWND_T(self.hwnd), None, byref(pt_dst), byref(size), self.hdc,
                byref(wintypes.POINT(0, 0)), 0, byref(self.blend), ULW_ALPHA))
        return bool(user32.UpdateLayeredWindow(
            HWND_T(self.hwnd), None, None, None, self.hdc,
            byref(wintypes.POINT(0, 0)), 0, byref(self.blend), ULW_ALPHA))

    def close(self) -> None:
        try:
            if self.hbm:
                gdi32.DeleteObject(self.hbm)
            if self.hdc:
                gdi32.DeleteDC(self.hdc)
            if self.hdc_screen:
                user32.ReleaseDC(None, self.hdc_screen)
        except Exception:
            pass


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


# ---------- 桌面层覆盖窗口协同：Progman 压到所有覆盖窗口之下 ----------

_overlays: list[int] = []
_NOMOVE_NOSIZE_NOACTIVATE = 0x2 | 0x1 | 0x10


def register_overlay(hwnd) -> None:
    """登记桌面层覆盖窗口（控件/频谱面板/歌词）。"""
    h = int(hwnd)
    if h not in _overlays:
        _overlays.append(h)


def seat_overlays() -> bool:
    """把 Progman 插到所有已登记覆盖窗口之下；z-order 已正确时零写操作。"""
    progman = user32.FindWindowW("Progman", None)
    if not progman or not _overlays:
        return False
    if user32.GetWindow(progman, GW_HWNDPREV) == HWND_T(_overlays[0]):
        return True
    user32.SetWindowPos(progman, HWND_T(_overlays[0]), 0, 0, 0, 0, _NOMOVE_NOSIZE_NOACTIVATE)
    for h in _overlays[1:]:
        user32.SetWindowPos(HWND_T(h), HWND_T(_overlays[0]), 0, 0, 0, 0,
                            _NOMOVE_NOSIZE_NOACTIVATE)
    return True
