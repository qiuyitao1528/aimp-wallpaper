"""IPC 重连修复的离线冒烟：不依赖 AIMP 运行，只验证三个关键机制。

1. 窗口类二次注册（1410）被容忍——修复前第二个接收窗会创建失败 → 僵尸连接
2. 向接收窗 PostMessage(WM_QUIT) 能退出 GetMessage 泵——_lose_aimp 退泵重连的前提
3. _lose_aimp/_drop_connection 状态序列在无 AIMP 时也安全
"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from aimp_wallpaper.aimp_api import AimpIPC, user32, wintypes

ok = True

# 1) 类已注册复用：同一实例连续建两个接收窗（进程级唯一回调 + hwnd 路由登记）
ipc = AimpIPC(poll_ms=200)
h1 = ipc._make_receiver()
h2 = ipc._make_receiver()
if h1 and h2:
    from aimp_wallpaper import aimp_api
    routed = aimp_api._BY_HWND.get(h1) is ipc and aimp_api._BY_HWND.get(h2) is ipc
    print(f"[PASS] 类复用: hwnd1={h1:#x} hwnd2={h2:#x} 路由登记={'OK' if routed else '缺失'}")
    ok = ok and routed
else:
    print(f"[FAIL] 类复用失败: hwnd1={h1} hwnd2={h2}（1410 未被容忍？）")
    ok = False

# 2) WM_QUIT 退泵：GetMessageW 应回 0
user32.PostMessageW(h2, 0x0012, 0, 0)  # WM_QUIT
msg = wintypes.MSG()
r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
if r == 0:
    print("[PASS] WM_QUIT 退泵: GetMessageW 返回 0")
else:
    print(f"[FAIL] WM_QUIT 未退泵: GetMessageW 返回 {r}")
    ok = False

# 3) 掉线状态序列安全（无 AIMP、无 recv/buf 也不炸）
ipc2 = AimpIPC(poll_ms=200)
ipc2._lose_aimp()
s = ipc2.snapshot()
if not s["connected"] and s["state"] == -1:
    print("[PASS] _lose_aimp 无连接时状态安全: connected=False state=-1")
else:
    print(f"[FAIL] _lose_aimp 状态异常: {s['connected']} {s['state']}")
    ok = False
ipc2._drop_connection()  # 空连接下重复清理也不炸
print("[PASS] _drop_connection 空连接幂等")

# 收尾：销毁测试窗口
for h in (h1, h2):
    if h:
        user32.DestroyWindow(h)

# 4) 线程空转 1.5s（AIMP 不在 → 连不上 → 5s 重试循环内不应崩）
ipc3 = AimpIPC(poll_ms=200)
ipc3.start()
time.sleep(1.5)
ipc3.shutdown()
ipc3.join(timeout=3.0)
if not ipc3.is_alive():
    print("[PASS] IPC 线程无 AIMP 时空转+正常退出")
else:
    print("[FAIL] IPC 线程未退出")
    ok = False

print("RESULT:", "ALL_PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
