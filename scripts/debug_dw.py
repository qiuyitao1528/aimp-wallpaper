# -*- coding: utf-8 -*-
"""分步调试 IDesktopWallpaper COM 声明。"""
import traceback

import comtypes
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
from ctypes import POINTER, wintypes


class IDW1(IUnknown):
    _iid_ = GUID("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")
    _idlflags_ = []
    _methods_ = [
        COMMETHOD([], HRESULT, "SetWallpaper",
                  (["in"], wintypes.LPCWSTR, "monitorID"),
                  (["in"], wintypes.LPCWSTR, "wallpaper")),
        COMMETHOD([], HRESULT, "GetWallpaper",
                  (["in"], wintypes.LPCWSTR, "monitorID"),
                  (["out"], POINTER(wintypes.LPWSTR), "wallpaper")),
        COMMETHOD([], HRESULT, "GetMonitorDevicePathAt",
                  (["in"], wintypes.UINT, "index"),
                  (["out"], POINTER(wintypes.LPWSTR), "monitorID")),
        COMMETHOD([], HRESULT, "GetMonitorDevicePathCount",
                  (["out"], POINTER(wintypes.UINT), "count")),
        COMMETHOD([], HRESULT, "GetMonitorRECT",
                  (["in"], wintypes.LPCWSTR, "monitorID"),
                  (["out"], POINTER(wintypes.RECT), "rect")),
        COMMETHOD([], HRESULT, "SetBackgroundColor",
                  (["in"], wintypes.COLORREF, "color")),
        COMMETHOD([], HRESULT, "GetBackgroundColor",
                  (["out"], POINTER(wintypes.COLORREF), "color")),
        COMMETHOD([], HRESULT, "SetPosition",
                  (["in"], wintypes.DWORD, "position")),
        COMMETHOD([], HRESULT, "GetPosition",
                  (["out"], POINTER(wintypes.DWORD), "position")),
    ]


CLSID = GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")

comtypes.CoInitialize()
print("step1: CoCreateInstance(无接口参数, 取 IUnknown)")
try:
    unk = comtypes.CoCreateInstance(CLSID, clsctx=comtypes.CLSCTX_ALL)
    print("  ok:", unk)
except Exception:
    traceback.print_exc()

print("step2: QI -> IDW1")
try:
    obj = unk.QueryInterface(IDW1)
    print("  ok:", obj)
except Exception:
    traceback.print_exc()
    obj = None

if obj:
    print("step3: GetMonitorDevicePathCount")
    try:
        n = obj.GetMonitorDevicePathCount()
        print("  count =", n)
        for i in range(n):
            mid = obj.GetMonitorDevicePathAt(i)
            rc = obj.GetMonitorRECT(mid)
            print(f"  [{i}] {mid} -> {rc.right - rc.left}x{rc.bottom - rc.top}")
        print("  GetPosition =", obj.GetPosition())
        print("  GetWallpaper =", obj.GetWallpaper(obj.GetMonitorDevicePathAt(0)))
    except Exception:
        traceback.print_exc()
