# -*- coding: utf-8 -*-
"""裸 ctypes 验证 IDesktopWallpaper 的 CLSID/IID（绕开 comtypes 的调用层）。"""
import ctypes
from ctypes import wintypes
from comtypes import GUID

ole32 = ctypes.windll.ole32
ole32.CoInitialize(None)
ole32.CoCreateInstance.restype = ctypes.HRESULT
ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_void_p)]

CLSCTX_ALL = 1 | 2 | 4 | 16
CLSID_DW = GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")

candidates = {
    "A802(现用)": "{B92B56A9-8BCC-4962-A802-5A5EA37A39C0}",
}

for name, iid_str in candidates.items():
    iid = GUID(iid_str)
    ppv = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(CLSID_DW), None, CLSCTX_ALL, ctypes.byref(iid), ctypes.byref(ppv))
    print(f"{name}: hr=0x{hr & 0xFFFFFFFF:08X} {'成功 ptr=' + hex(ppv.value) if hr == 0 else ''}")
