# -*- coding: utf-8 -*-
"""加线程级异常钩子：worker/托盘等线程崩溃时写日志（此前静默崩溃很难发现）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\__main__.py"
s = io.open(P, encoding="utf-8").read()

anchor = '    sys.excepthook = lambda t, v, tb: applog.log_exc("未捕获异常:\\n", t, v, tb)'
add = anchor + '''
    # 线程内的异常默认只打印到不可见的 stderr（--windowed 下等于消失），这里统一落盘
    threading.excepthook = lambda a: applog.log_exc(
        f"线程 {getattr(a.thread, 'name', '?')} 异常:\\n", a.exc_type, a.exc_value, a.exc_traceback)'''

if "threading.excepthook" in s:
    print("已存在")
elif anchor in s:
    io.open(P, "w", encoding="utf-8").write(s.replace(anchor, add, 1))
    print("已加线程异常钩子")
else:
    print("未找到锚点")
