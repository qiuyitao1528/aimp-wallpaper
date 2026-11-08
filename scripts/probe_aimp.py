# -*- coding: utf-8 -*-
"""AIMP Remote API 实地探针（只读，不改播放状态）。

实测三件事：
1. 窗口/共享内存是否存在，共享内存 2048 字节的真实布局
2. WM_AIMP_PROPERTY 各属性 GET 的返回值
3. 注册通知后能否收到 WM_AIMP_NOTIFY；请求封面能否收到 WM_COPYDATA 图片流
结果落盘：scripts/probe_result.md + cover_probe.img
"""
import ctypes
import os
import sys
import time
from ctypes import POINTER, byref, cast, c_ssize_t, c_void_p
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
# 64 位句柄/指针必须声明 restype，否则被截断成 32 位 int（读共享内存必崩）
kernel32.OpenFileMappingW.restype = c_void_p
kernel32.MapViewOfFile.restype = c_void_p
kernel32.MapViewOfFile.argtypes = [c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
kernel32.UnmapViewOfFile.argtypes = [c_void_p]
kernel32.UnmapViewOfFile.restype = wintypes.BOOL

# ---- 常量（源自官方 apiRemote.h，三源核证）----
WM_USER = 0x0400
WM_AIMP_COMMAND = WM_USER + 0x75
WM_AIMP_PROPERTY = WM_USER + 0x77
WM_AIMP_NOTIFY = WM_USER + 0x76
WM_COPYDATA = 0x004A

P_VERSION, P_POSITION, P_DURATION, P_STATE, P_VOLUME, P_MUTE = 0x10, 0x20, 0x30, 0x40, 0x50, 0x60
CMD_REGISTER_NOTIFY, CMD_UNREGISTER_NOTIFY = 11, 12
CMD_GET_ALBUMART = 29
ALBUMART_MAGIC = 0x41495043  # "AIPC"

LRESULT = c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [("dwData", c_ssize_t), ("cbData", wintypes.DWORD), ("lpData", c_void_p)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


OUT_DIR = os.path.dirname(os.path.abspath(__file__))
cover_path = os.path.join(OUT_DIR, "cover_probe.img")
log_lines = []


def log(s=""):
    print(s)
    log_lines.append(str(s))


got = {"cover": False, "cover_size": 0, "notifies": []}


def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_COPYDATA:
        cds = cast(lparam, POINTER(COPYDATASTRUCT)).contents
        log(f"  [COPYDATA] dwData=0x{cds.dwData:08X} cbData={cds.cbData}")
        if cds.dwData == ALBUMART_MAGIC:
            data = ctypes.string_at(cds.lpData, cds.cbData)
            with open(cover_path, "wb") as f:
                f.write(data)
            got["cover"] = True
            got["cover_size"] = cds.cbData
        return 1
    if msg == WM_AIMP_NOTIFY:
        got["notifies"].append((int(wparam), int(lparam)))
        log(f"  [NOTIFY] wParam={wparam} lParam={lparam & 0xFFFFFFFF}")
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def make_window(name):
    wc = WNDCLASSW()
    wc.lpfnWndProc = WNDPROC(wnd_proc)
    wc.lpszClassName = name
    wc.hInstance = kernel32.GetModuleHandleW(None)
    atom = user32.RegisterClassW(byref(wc))
    if not atom:
        return None, None
    # 先试 message-only（父窗口 HWND_MESSAGE）；失败再建普通隐藏窗
    hwnd = user32.CreateWindowExW(0, name, name, 0, 0, 0, 0, 0, wintypes.HWND(-3), None, wc.hInstance, None)
    if not hwnd:
        hwnd = user32.CreateWindowExW(0, name, name, 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
    return hwnd, wc


def pump(seconds):
    end = time.time() + seconds
    msg = wintypes.MSG()
    while time.time() < end:
        while user32.PeekMessageW(byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
        time.sleep(0.05)


def prop(hwnd, pid):
    return user32.SendMessageW(hwnd, WM_AIMP_PROPERTY, pid | 0, None)


def hexdump(data, limit=160):
    lines = []
    for i in range(0, min(len(data), limit), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02X}" for b in chunk)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:04X}: {hx:<48} {txt}")
    return "\n".join(lines)


def utf16_runs(data):
    """把缓冲按 UTF-16LE 解码，输出可读字符串段及其偏移。"""
    out = []
    cur, start = [], None
    for i in range(0, len(data) - 1, 2):
        ch = data[i] | (data[i + 1] << 8)
        printable = 0x20 <= ch < 0xFFFE and not (0xD800 <= ch < 0xE000)
        if printable:
            if start is None:
                start = i
            cur.append(chr(ch))
        else:
            if start is not None and len(cur) >= 2:
                out.append((start, "".join(cur)))
            cur, start = [], None
    if start is not None and len(cur) >= 2:
        out.append((start, "".join(cur)))
    return out


def main():
    log("# AIMP 探针结果")
    log(f"\n## 1. 窗口")
    hwnd = user32.FindWindowW("AIMP2_RemoteInfo", None)
    log(f"FindWindow(AIMP2_RemoteInfo) = {hwnd:#x}" if hwnd else "FindWindow(AIMP2_RemoteInfo) = 无")
    if not hwnd:
        log("AIMP 未运行，退出")
        return 1

    log(f"\n## 2. 属性 GET（SendMessage 返回值）")
    for name, pid in [("VERSION", P_VERSION), ("STATE", P_STATE), ("POSITION_ms", P_POSITION),
                      ("DURATION_ms", P_DURATION), ("VOLUME", P_VOLUME), ("MUTE", P_MUTE)]:
        v = prop(hwnd, pid)
        hi, lo = (v >> 16) & 0xFFFF, v & 0xFFFF
        log(f"  {name:<12} = {v} (0x{v & 0xFFFFFFFF:08X}) hi={hi} lo={lo}")

    log(f"\n## 3. 共享内存")
    FILE_MAP_READ = 4
    mapping = None
    used_name = None
    for nm in ("AIMP2_RemoteInfo", "AIMP_RemoteInfo", "AIMP_FileInfo", "AIMP2_FileInfo"):
        h = kernel32.OpenFileMappingW(FILE_MAP_READ, False, nm)
        log(f"  OpenFileMapping({nm}) = {'OK' if h else '无'}")
        if h and not mapping:
            mapping, used_name = h, nm
    if not mapping:
        log("  没有找到任何共享内存映射名！")
        return 1
    buf = kernel32.MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0)  # 0=映射整个区域
    if not buf:
        log("  MapViewOfFile 失败")
        return 1
    data = None
    for size in (2048, 1024, 512):
        try:
            data = ctypes.string_at(buf, size)
            log(f"  实际可读 {size} 字节")
            break
        except OSError as e:
            log(f"  读 {size} 字节失败：{e}")
    kernel32.UnmapViewOfFile(buf)
    if data is None:
        return 1
    log(f"  使用映射名：{used_name}")
    log(f"  前 160 字节：\n{hexdump(data)}")
    log(f"  UTF-16 可读段（偏移: 文本）：")
    for off, txt in utf16_runs(data):
        log(f"    0x{off:04X}: {txt!r}")
    dw0 = int.from_bytes(data[0:4], "little")
    log(f"  DWORD@0x00 = {dw0} (0x{dw0:08X})")
    for off in (0x04, 0x08, 0x50, 0x54, 0x58):
        dw = int.from_bytes(data[off:off + 4], "little")
        log(f"  DWORD@0x{off:02X} = {dw} (0x{dw:08X})")

    log(f"\n## 4. 通知 + 封面（建接收窗口）")
    hwnd_r, wc = make_window("AIMP_WP_Probe")
    log(f"  接收窗口 = {hwnd_r:#x}" if hwnd_r else "  接收窗口创建失败")
    if hwnd_r:
        r = user32.SendMessageW(hwnd_aimp := hwnd, WM_AIMP_COMMAND, CMD_REGISTER_NOTIFY, hwnd_r)
        log(f"  REGISTER_NOTIFY -> {r}")
        pump(0.5)
        r = user32.SendMessageW(hwnd_aimp, WM_AIMP_COMMAND, CMD_GET_ALBUMART, hwnd_r)
        log(f"  GET_ALBUMART -> {r}")
        pump(3.0)
        log(f"  通知收到 {len(got['notifies'])} 条：{got['notifies'][:20]}")
        log(f"  封面收到 = {got['cover']}，{got['cover_size']} 字节 -> {cover_path}")
        user32.SendMessageW(hwnd_aimp, WM_AIMP_COMMAND, CMD_UNREGISTER_NOTIFY, hwnd_r)
        user32.DestroyWindow(hwnd_r)
        user32.UnregisterClassW(wc.lpszClassName, wc.hInstance)

    with open(os.path.join(OUT_DIR, "probe_result.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
