# -*- coding: utf-8 -*-
"""探针 v2：1) 当前曲目元数据+封面实测  2) 连切 3 首测封面  3) 可视化窗口屏外抓取。"""
import ctypes
import io
import sys
import time
from ctypes import POINTER, byref, c_ssize_t, c_size_t, c_void_p
from ctypes import wintypes

sys.path.insert(0, r"E:\aimp-wallpaper")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

HWND_T, WPARAM, LPARAM, LRESULT = c_void_p, c_size_t, c_ssize_t, c_ssize_t
UINT = wintypes.UINT
user32.FindWindowW.restype = HWND_T
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = HWND_T
user32.FindWindowExW.argtypes = [HWND_T, HWND_T, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [HWND_T, UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [HWND_T, UINT, WPARAM, LPARAM]
user32.GetWindowRect.argtypes = [HWND_T, POINTER(wintypes.RECT)]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [HWND_T]
user32.ShowWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [HWND_T, ctypes.c_int]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [HWND_T, HWND_T, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, UINT]
user32.GetWindowLongPtrW.restype = c_ssize_t
user32.GetWindowLongPtrW.argtypes = [HWND_T, ctypes.c_int]
user32.SetWindowLongPtrW.restype = c_ssize_t
user32.SetWindowLongPtrW.argtypes = [HWND_T, ctypes.c_int, c_ssize_t]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.restype = HWND_T
user32.CreateWindowExW.argtypes = [UINT, wintypes.LPCWSTR, wintypes.LPCWSTR, UINT,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   HWND_T, c_void_p, c_void_p, c_void_p]
user32.DestroyWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [HWND_T]
user32.UnregisterClassW.restype = wintypes.BOOL
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, c_void_p]
kernel32.GetModuleHandleW.restype = c_void_p
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.OpenFileMappingW.restype = c_void_p
kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.MapViewOfFile.restype = c_void_p
kernel32.MapViewOfFile.argtypes = [c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, c_size_t]
kernel32.UnmapViewOfFile.argtypes = [c_void_p]

WM_USER = 0x400
WM_AIMP_COMMAND = WM_USER + 0x75
WM_COPYDATA = 0x4A
CMD_GET_ALBUMART, CMD_NEXT = 29, 17
ALBUMART_MAGIC = 0x41495043
SW_SHOWNA, SW_HIDE = 8, 0
SWP_NOACTIVATE, SWP_NOZORDER, SWP_NOSIZE = 0x10, 0x4, 0x1
HWND_BOTTOM = 1
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80

KEEPALIVE = []  # 防 GC


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [("dwData", c_size_t), ("cbData", wintypes.DWORD), ("lpData", c_void_p)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", ctypes.WINFUNCTYPE(LRESULT, HWND_T, UINT, WPARAM, LPARAM)),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", c_void_p),
                ("hIcon", c_void_p), ("hCursor", c_void_p), ("hbrBackground", c_void_p),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


got = {"cover": None}


def make_recv():
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND_T, UINT, WPARAM, LPARAM)

    def wp(hwnd, msg, w, l):
        if msg == WM_COPYDATA:
            cds = ctypes.cast(l, POINTER(COPYDATASTRUCT)).contents
            if cds.dwData == ALBUMART_MAGIC and cds.cbData:
                got["cover"] = ctypes.string_at(cds.lpData, cds.cbData)
            return 1
        return user32.DefWindowProcW(hwnd, msg, w, l)

    wndproc = WNDPROC(wp)
    wc = WNDCLASSW()
    wc.lpfnWndProc = wndproc
    wc.lpszClassName = "AIMP_WP_Probe2"
    wc.hInstance = kernel32.GetModuleHandleW(None)
    user32.RegisterClassW(byref(wc))
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, wc.lpszClassName, 0, 0, 0, 0, 0,
                                  HWND_T(-3), None, wc.hInstance, None)
    KEEPALIVE.extend([wndproc, wc])  # 关键：防 GC 弄挂 wndproc
    return hwnd


def read_fileinfo():
    m = kernel32.OpenFileMappingW(4, False, "AIMP2_RemoteInfo")
    if not m:
        return None
    buf = kernel32.MapViewOfFile(m, 4, 0, 0, 0)
    data = ctypes.string_at(buf, 2048)
    kernel32.UnmapViewOfFile(buf)
    from aimp_wallpaper.aimp_api import parse_fileinfo
    return parse_fileinfo(data)


def request_cover(aimp, recv):
    got["cover"] = None
    r = user32.SendMessageW(aimp, WM_AIMP_COMMAND, CMD_GET_ALBUMART, LPARAM(recv))
    time.sleep(0.2)
    n = len(got["cover"]) if got["cover"] else 0
    what = ""
    if n:
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(got["cover"]))
            what = f" {im.format} {im.size}"
        except OSError:
            what = " (无法解码)"
    print(f"  GET_ALBUMART -> {r}, 封面 {n} 字节{what}")
    return got["cover"]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class RGBQUAD(ctypes.Structure):
    _fields_ = [("rgbBlue", ctypes.c_ubyte), ("rgbGreen", ctypes.c_ubyte), ("rgbRed", ctypes.c_ubyte),
                ("rgbReserved", ctypes.c_ubyte)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 2)]


def grab(hwnd, path):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        print(f"  grab {hwnd:#x}: 尺寸无效")
        return
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)
    bi = BITMAPINFOHEADER(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bmi = BITMAPINFO()
    bmi.bmiHeader = bi
    pixels = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, pixels, byref(bmi), 0)
    from PIL import Image
    Image.frombuffer("RGBA", (w, h), bytes(pixels), "raw", "BGRA", w * 4, 0).save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    print(f"  grab {hwnd:#x} {w}x{h} PrintWindow={ok} -> {path}")


aimp = user32.FindWindowW("AIMP2_RemoteInfo", None)
recv = make_recv()

FULL = "--full" in sys.argv

print("== 1) 当前曲目 + 封面 ==")
print(f"  曲目: {read_fileinfo()}")
request_cover(aimp, recv)

if FULL:
    print("== 2) 连切 3 首测封面 ==")
    for i in range(3):
        user32.SendMessageW(aimp, WM_AIMP_COMMAND, CMD_NEXT, 0)
        time.sleep(1.2)
        info = read_fileinfo()
        print(f"  切到: {info['title']!r} / {info['artist']!r} / {info['filename'][:60]!r}")
        request_cover(aimp, recv)
        if got["cover"]:
            open(rf"E:\aimp-wallpaper\scripts\cover_next{i}.img", "wb").write(got["cover"])

print("== 3) 可视化窗口 ==")
vis = user32.FindWindowExW(None, None, "TASEScene", "可视化")
print(f"  可视化窗口 = {vis:#x} 可见={bool(user32.IsWindowVisible(vis))}")
if vis:
    orig = wintypes.RECT()
    user32.GetWindowRect(vis, byref(orig))
    ex_orig = user32.GetWindowLongPtrW(vis, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(vis, GWL_EXSTYLE, ex_orig | WS_EX_TOOLWINDOW)
    user32.ShowWindow(vis, SW_SHOWNA)
    user32.SetWindowPos(vis, HWND_T(-32000) if False else HWND_T(1), -32000, -32000, 0, 0,
                        SWP_NOACTIVATE | SWP_NOZORDER | SWP_NOSIZE)
    time.sleep(1.2)
    grab(vis, r"E:\aimp-wallpaper\scripts\vis_capture.png")
    time.sleep(0.6)
    grab(vis, r"E:\aimp-wallpaper\scripts\vis_capture2.png")
    mainf = user32.FindWindowExW(None, None, "TAIMPMainForm", None)
    if mainf:
        grab(mainf, r"E:\aimp-wallpaper\scripts\aimp_main.png")
    user32.ShowWindow(vis, SW_HIDE)
    user32.SetWindowLongPtrW(vis, GWL_EXSTYLE, ex_orig)
    print("  已还原可视化窗口隐藏状态")
