"""极简文件日志：output_dir/aimp-wallpaper.log，超 256KB 整文件重建。

--windowed 应用无控制台，Tk 回调/线程异常全部隐形；所有关键路径和未捕获
异常写到这里，出问题看日志即可定位。
"""
from __future__ import annotations

import os
import threading
import time

_PATH: str | None = None
_LOCK = threading.Lock()
MAX_BYTES = 262144


def init(path: str) -> None:
    global _PATH
    _PATH = path


def log(msg: str) -> None:
    if not _PATH:
        return
    line = f"{time.strftime('%m-%d %H:%M:%S')} [{threading.current_thread().name}] {msg}"
    with _LOCK:
        try:
            if os.path.exists(_PATH) and os.path.getsize(_PATH) > MAX_BYTES:
                os.remove(_PATH)
            with open(_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def log_exc(prefix: str, exc_type, exc_val, exc_tb) -> None:
    import traceback
    log(prefix + "".join(traceback.format_exception(exc_type, exc_val, exc_tb)))
