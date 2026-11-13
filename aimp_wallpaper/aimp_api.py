"""AIMP Remote API 封装：窗口消息 + 共享内存元数据 + WM_COPYDATA 封面推送。

所有常量与交互方式均在本机 AIMP v5.40.2727 实测验证（scripts/probe_aimp.py）：
- FindWindow("AIMP2_RemoteInfo") 取 AIMP 消息窗口
- WM_AIMP_COMMAND = WM_USER+0x75（命令），WM_AIMP_PROPERTY = WM_USER+0x77（属性 GET/SET）
- 共享内存映射名 AIMP2_RemoteInfo，2048 字节：
  0x00=字符串区起始偏移(0x58)，0x08=比特率kbps，0x0C=声道，0x10=时长ms，0x20=采样率，
  0x28 起依次 Album/Artist/Date/FileName/Genre/Title 的字符长度（WCHAR 个数），
  0x58 起按同样顺序紧凑排 UTF-16LE（无终止符）
- 封面：CMD_GET_ALBUMART(29) 且 lParam=接收窗口 → AIMP 回 WM_COPYDATA（dwData=0x41495043，lpData=图片字节流）
- 通知：CMD_REGISTER_NOTIFY(11) 注册后收 WM_AIMP_NOTIFY：wParam 1=切歌 2=电台换曲 3=属性变化(lParam=属性ID)
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import POINTER, byref, c_int, c_ssize_t, c_size_t, c_void_p, cast, string_at
from ctypes import wintypes

from . import applog

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---- Win32 类型（64 位指针全部显式声明，避免 ctypes 默认 32 位截断）----
HWND = c_void_p
WPARAM = c_size_t
LPARAM = c_ssize_t
LRESULT = c_ssize_t
UINT = ctypes.c_uint
BOOL = wintypes.BOOL
LPVOID = c_void_p
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

kernel32.OpenFileMappingW.restype = c_void_p
kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, BOOL, wintypes.LPCWSTR]
kernel32.MapViewOfFile.restype = c_void_p
kernel32.MapViewOfFile.argtypes = [c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, c_size_t]
kernel32.UnmapViewOfFile.argtypes = [c_void_p]

user32.FindWindowW.restype = c_void_p
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.PostMessageW.restype = BOOL
user32.PostMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.GetMessageW.restype = c_ssize_t
user32.GetMessageW.argtypes = [POINTER(wintypes.MSG), HWND, UINT, UINT]
user32.TranslateMessage.argtypes = [POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [POINTER(wintypes.MSG)]
user32.SetTimer.restype = c_size_t
user32.SetTimer.argtypes = [HWND, c_size_t, UINT, LPVOID]
user32.DestroyWindow.restype = BOOL
user32.DestroyWindow.argtypes = [HWND]
kernel32.GetModuleHandleW.restype = c_void_p
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [("dwData", c_size_t), ("cbData", wintypes.DWORD), ("lpData", c_void_p)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", c_void_p), ("hIcon", c_void_p),
        ("hCursor", c_void_p), ("hbrBackground", c_void_p), ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32.RegisterClassW.restype = wintypes.ATOM
user32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]
user32.CreateWindowExW.restype = HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   c_int, c_int, c_int, c_int, HWND, c_void_p, c_void_p, c_void_p]


# ---- AIMP 协议常量 ----
WM_USER = 0x0400
WM_AIMP_COMMAND = WM_USER + 0x75
WM_AIMP_PROPERTY = WM_USER + 0x77
WM_AIMP_NOTIFY = WM_USER + 0x76
WM_COPYDATA = 0x004A
WM_TIMER = 0x0113
WM_DESTROY = 0x0002

STATE_NO_AIMP, STATE_STOPPED, STATE_PAUSED, STATE_PLAYING = -1, 0, 1, 2

P_VERSION, P_POSITION, P_DURATION, P_STATE = 0x10, 0x20, 0x30, 0x40
CMD_REGISTER_NOTIFY, CMD_UNREGISTER_NOTIFY = 11, 12
CMD_PLAY, CMD_PLAYPAUSE, CMD_PAUSE, CMD_STOP, CMD_NEXT, CMD_PREV = 13, 14, 15, 16, 17, 18
CMD_GET_ALBUMART = 29
ALBUMART_MAGIC = 0x41495043  # "AIPC"

_SMTO_ABORTIFHUNG = 2

user32.SendMessageTimeoutW.restype = c_ssize_t  # LRESULT 64 位：默认 c_int 会截断回值
user32.SendMessageTimeoutW.argtypes = [HWND, UINT, WPARAM, LPARAM, UINT, UINT, POINTER(c_size_t)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _send_timeout(hwnd, msg, wparam, lparam, timeout_ms=1000) -> int:
    """带超时的 SendMessage：AIMP 挂死/模态卡住时，IPC 线程绝不能卡死在内核
    调用里（同步 SendMessageW 无超时，一旦目标不回消息线程就永久停摆）。"""
    dummy = c_size_t()
    r = user32.SendMessageTimeoutW(hwnd, msg, WPARAM(wparam), LPARAM(lparam),
                                   _SMTO_ABORTIFHUNG, timeout_ms, byref(dummy))
    return int(r)

AIMP_CLASS = "AIMP2_RemoteInfo"
SHARED_SIZE = 2048
STR_FIELDS = ("album", "artist", "date", "filename", "genre", "title")  # 0x28 起 + 0x58 起，顺序实测确认

# 接收窗类进程级注册：WNDPROC 回调对象必须与窗口类同寿命（只建一次，永不释放）。
# 此前重连时每次新建回调并覆盖引用，类里登记的旧回调被 GC 后，WM_TIMER 派发
# 跳进已释放内存 → access violation（实测地址 0x113=WM_TIMER），IPC 线程整体死亡。
_RECV_CLASS = "AIMP_WP_Receiver"
_BY_HWND: dict = {}     # hwnd -> AimpIPC 实例（消息路由）
_CLASS_OK = False
_WNDPROC_CB = None


def _receiver_dispatch(hwnd, msg, wparam, lparam):
    """进程级消息派发：按 hwnd 路由到实例；单条消息异常落日志，不崩线程。"""
    ipc = _BY_HWND.get(hwnd)
    if ipc is None:
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    try:
        return ipc._wndproc(hwnd, msg, wparam, lparam)
    except Exception:
        applog.log_exc("接收窗消息处理异常:\n", *sys.exc_info())
        return 0


def _ensure_receiver_class() -> bool:
    global _CLASS_OK, _WNDPROC_CB
    if _CLASS_OK:
        return True
    if _WNDPROC_CB is None:
        _WNDPROC_CB = WNDPROC(_receiver_dispatch)
    wc = WNDCLASSW()
    wc.lpfnWndProc = _WNDPROC_CB
    wc.lpszClassName = _RECV_CLASS
    wc.hInstance = kernel32.GetModuleHandleW(None)
    if not user32.RegisterClassW(byref(wc)) and ctypes.get_last_error() != 1410:
        return False
    _CLASS_OK = True
    return True


def _clean_text(s: str) -> str:
    """清掉常见渲染成豆腐块的字符：PUA、emoji 增补区、变体选择符、零宽字符。"""
    if not s:
        return s
    out = []
    for ch in s:
        o = ord(ch)
        if o in (0x200B, 0x200C, 0x200D, 0xFEFF) or 0xE000 <= o <= 0xF8FF \
                or 0xFE00 <= o <= 0xFE0F or o >= 0x1F000:
            continue
        out.append(" " if ch in "\r\n\t" else ch)
    return "".join(out).strip()


def parse_fileinfo(data: bytes) -> dict | None:
    """解析共享内存 AIMP2FileInfo（布局见模块 docstring，已按实测校准）。"""
    if not data or len(data) < 0x58:
        return None
    strings_off = int.from_bytes(data[0x00:0x04], "little")
    if strings_off < 0x28 or strings_off >= len(data):
        strings_off = 0x58
    lens = {}
    for i, key in enumerate(STR_FIELDS):
        off = 0x28 + i * 4
        lens[key] = int.from_bytes(data[off:off + 4], "little")
    out, pos = {}, strings_off
    for key in STR_FIELDS:
        n = lens.get(key, 0)
        if not isinstance(n, int) or n < 0 or pos + n * 2 > len(data):
            n = 0
        out[key] = _clean_text(data[pos:pos + n * 2].decode("utf-16-le", errors="replace").rstrip("\x00")) if n else ""
        pos += n * 2
    # 音频参数（AIMP 直读，字段偏移按官方 AIMPRemoteAccess 结构校准）：
    #   0x04=Active  0x08=BitRate(kbps)  0x0C=Channels  0x10=Duration(ms)
    #   0x14=FileSize(bytes)  0x20=SampleRate(Hz)  0x24=TrackNumber
    u32 = lambda off: int.from_bytes(data[off:off + 4], "little")
    out["bit_rate"] = u32(0x08)
    out["channels"] = u32(0x0C)
    out["duration_ms"] = u32(0x10)
    out["file_size"] = u32(0x14)
    out["samplerate"] = u32(0x20)
    out["track_number"] = u32(0x24)
    return out


class AimpIPC(threading.Thread):
    """后台线程：持有 AIMP 连接、收封面/通知、周期轮询；对外提供快照与控制命令。"""

    def __init__(self, poll_ms=120):
        super().__init__(daemon=True, name="aimp-ipc")
        self._poll_ms = poll_ms
        self._lock = threading.Lock()
        self._track_evt = threading.Event()   # 切歌信号
        self._cover_evt = threading.Event()   # 当前代封面已就绪（或确认无封面）
        self._stop_evt = threading.Event()
        self._gen = 0                          # 曲目代数：切歌 +1
        self._snap = {
            "connected": False, "state": STATE_NO_AIMP,
            "position_ms": 0, "duration_ms": 0,
            "file_size": 0, "samplerate": 0, "bit_rate": 0, "channels": 0,
            "title": "", "artist": "", "album": "", "filename": "",
            "cover_gen": 0,
        }
        self._cover_bytes = None
        self._cover_retry_until = 0.0
        self._cover_next_try = 0.0
        self._cover_req_gen = 0        # 封面请求所属代数：拒收上一首的迟到回图
        self._cand_sig = None          # 去抖：候选签名
        self._cand_since = 0.0
        self._committed_sig = None     # 上次真正换代的签名
        self._aimp = None
        self._recv = None
        self._mapping = None
        self._buf = None
        self._timer_id = 0

    # ---------- 对外接口 ----------

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._snap)

    def wait_track_change(self, timeout=None) -> int:
        """阻塞等待切歌，返回新曲目代数；timeout 到点返回当前代数。"""
        self._track_evt.wait(timeout)
        self._track_evt.clear()
        with self._lock:
            return self._gen

    def wait_cover(self, gen, timeout=4.0) -> bytes | None:
        """等待指定代数的封面字节流；无封面/超时返回 None。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._snap["cover_gen"] == gen and self._cover_evt.is_set():
                    return self._cover_bytes
                if self._snap["cover_gen"] != gen:
                    return None  # 已切到更新的曲目
            time.sleep(0.05)
        return None

    def cover_now(self, gen) -> bytes | None | object:
        """非阻塞取封面：就绪返回 bytes（无封面返回 False），未就绪返回 None。"""
        with self._lock:
            if self._snap["cover_gen"] == gen and self._cover_evt.is_set():
                return self._cover_bytes if self._cover_bytes else False
        return None

    # 控制命令：任意线程可直接调（纯 SendMessage，不碰共享状态）
    def play(self):        self._cmd(CMD_PLAY)
    def pause(self):       self._cmd(CMD_PAUSE)
    def playpause(self):   self._cmd(CMD_PLAYPAUSE)
    def stop(self):        self._cmd(CMD_STOP)
    def next(self):        self._cmd(CMD_NEXT)
    def prev(self):        self._cmd(CMD_PREV)

    def set_position(self, ms: int):
        if self._aimp:
            _send_timeout(self._aimp, WM_AIMP_PROPERTY, P_POSITION | 1, max(0, int(ms)))

    def shutdown(self):
        self._stop_evt.set()
        if self._recv:
            user32.PostMessageW(self._recv, 0x0012, 0, 0)  # WM_QUIT 退出消息泵

    # ---------- 内部 ----------

    def _cmd(self, n):
        if self._aimp:
            _send_timeout(self._aimp, WM_AIMP_COMMAND, n, 0)

    def _prop(self, pid) -> int:
        return int(_send_timeout(self._aimp, WM_AIMP_PROPERTY, pid | 0, 0) & 0xFFFFFFFF)

    def _request_cover(self):
        """换代后启动封面获取：延迟 300ms 首次请求（AIMP 常已就绪），2s 内每 500ms 快速重试，
        之后每秒重试，10s 内拿到即渲染；超时才判定无封面（画占位图）。"""
        with self._lock:
            self._cover_bytes = None
            self._cover_evt.clear()
            self._cover_req_gen = self._gen
        now = time.time()
        self._cover_retry_until = now + 10.0
        self._cover_next_try = now + 0.05
        self._cover_fast_until = now + 0.8

    def _try_cover_once(self):
        if not self._aimp or not self._cover_retry_until:
            return
        now = time.time()
        if now < self._cover_next_try:
            return
        self._cover_next_try = now + (0.06 if now < getattr(self, "_cover_fast_until", 0) else 0.5)
        # r==0 可能只是切歌瞬间还没解析好，不立即放弃，按窗口继续重试
        _send_timeout(self._aimp, WM_AIMP_COMMAND, CMD_GET_ALBUMART, self._recv or 0)

    def _on_track(self, force=False):
        """读元数据；签名去抖后若确实换曲 → 换代 + 请求封面 + 发事件。

        共享内存切换瞬间可能读到混合状态，故要求签名连续两次（≥0.5s）一致才提交；
        AIMP 的切歌通知（NOTIFY 1/2）视为可信，立即提交。
        """
        info = self._read_fileinfo()
        if not info:
            return
        sig = (info["album"], info["artist"], info["filename"], info["title"])
        if not force:
            if sig != self._cand_sig:
                self._cand_sig, self._cand_since = sig, time.time()
                return
            if time.time() - self._cand_since < 0.2:
                return
        self._cand_sig = None
        if sig == self._committed_sig:
            return  # 没换曲
        self._committed_sig = sig
        with self._lock:
            self._snap.update({
                "title": info["title"], "artist": info["artist"],
                "album": info["album"], "filename": info["filename"],
                # 音频参数直接取 AIMP（不经文件头解析，网络/移动盘也准）
                "file_size": info.get("file_size") or 0,
                "samplerate": info.get("samplerate") or 0,
                "bit_rate": info.get("bit_rate") or 0,
                "channels": info.get("channels") or 0,
            })
            self._gen += 1
            self._snap["cover_gen"] = self._gen
            # 时长总是跟随共享内存：此前 0 时保留旧值，切到电台/流媒体时
            # 歌词与歌曲信息行会用上一首歌的时长错位
            self._snap["duration_ms"] = int(info.get("duration_ms") or 0)
        self._request_cover()
        self._track_evt.set()

    def _read_fileinfo(self) -> dict | None:
        if not self._buf:
            return None
        try:
            data = string_at(self._buf, SHARED_SIZE)
        except OSError:
            return None
        return parse_fileinfo(data)

    def _connect(self) -> bool:
        hwnd = user32.FindWindowW(AIMP_CLASS, None)
        if not hwnd:
            return False
        self._aimp = hwnd
        kernel32.OpenFileMappingW.restype = c_void_p
        mapping = kernel32.OpenFileMappingW(4, False, AIMP_CLASS)  # FILE_MAP_READ
        if not mapping:
            self._aimp = None
            return False
        self._mapping = mapping
        self._buf = kernel32.MapViewOfFile(mapping, 4, 0, 0, 0)
        self._recv = self._make_receiver()
        if not self._recv:  # 接收窗建不起来：注册通知/轮询都没了，绝不能假装已连接
            kernel32.UnmapViewOfFile(self._buf)
            self._buf = None
            kernel32.CloseHandle(self._mapping)
            self._mapping = None
            self._aimp = None
            return False
        _send_timeout(hwnd, WM_AIMP_COMMAND, CMD_REGISTER_NOTIFY, self._recv)
        self._timer_id = user32.SetTimer(self._recv, 1, self._poll_ms, None)
        with self._lock:
            self._snap["connected"] = True
            self._snap["state"] = self._prop(P_STATE)
            self._snap["duration_ms"] = self._prop(P_DURATION)
        return True

    def _make_receiver(self):
        """建接收窗（message-only）。返回 hwnd 或 None；类与回调均进程级唯一。"""
        if not _ensure_receiver_class():
            return None
        hinst = kernel32.GetModuleHandleW(None)
        # message-only 窗口（实测能收 WM_COPYDATA 和 WM_AIMP_NOTIFY）
        hwnd = user32.CreateWindowExW(0, _RECV_CLASS, _RECV_CLASS, 0,
                                      0, 0, 0, 0, HWND(-3), None, hinst, None)
        if not hwnd:
            hwnd = user32.CreateWindowExW(0, _RECV_CLASS, _RECV_CLASS, 0,
                                          0, 0, 0, 0, None, None, hinst, None)
        if hwnd:
            _BY_HWND[hwnd] = self
        return hwnd

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_COPYDATA:
            cds = cast(lparam, POINTER(COPYDATASTRUCT)).contents
            if cds.dwData == ALBUMART_MAGIC and cds.cbData > 0:
                data = string_at(cds.lpData, cds.cbData)
                with self._lock:
                    # 只收当前代请求的回图：上一首请求的迟到回图直接丢弃（防封面串台）
                    if not self._cover_evt.is_set() and self._cover_req_gen == self._gen:
                        self._cover_bytes = data
                        self._cover_evt.set()
            return 1
        if msg == WM_AIMP_NOTIFY:
            wp = int(wparam)
            if wp in (1, 2):           # 切歌 / 电台换曲：可信，立即提交
                self._on_track(force=True)
            elif wp == 3 and int(lparam) & 0xFFFF == P_POSITION:
                with self._lock:       # 进度推进通知
                    self._snap["position_ms"] = self._prop(P_POSITION)
                    self._snap["duration_ms"] = self._prop(P_DURATION)
            return 0
        if msg == WM_TIMER:
            self._on_timer()
            return 0
        if msg == WM_DESTROY:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_timer(self):
        if not self._aimp:
            return
        # AIMP 进程是否还活着：WM_NULL 超时即失联（沿用既有判定语义）
        r = _send_timeout(self._aimp, 0x0000, 0, 0, 300)
        if not r:
            self._lose_aimp()  # AIMP 忙碌超 300ms ≠ 永久掉线：退泵重连
            return
        # 属性读取全部在锁外：此前有轮询在持锁状态下发 SendMessage，
        # AIMP 挂死时锁被无限持有，snapshot() 的所有消费线程跟着死锁
        state = self._prop(P_STATE)
        pos = self._prop(P_POSITION)
        dur = self._prop(P_DURATION)
        with self._lock:
            self._snap["state"] = state
            self._snap["position_ms"] = pos
            self._snap["duration_ms"] = dur
        self._on_track()
        # 封面重试窗口：还没拿到（evt 未置位）就按节拍重试，超窗放弃
        if self._cover_retry_until:
            with self._lock:
                waiting = not self._cover_evt.is_set()
            if waiting:
                if time.time() > self._cover_retry_until:
                    with self._lock:
                        self._cover_evt.set()  # 放弃 → 占位图
                    self._cover_retry_until = 0.0
                else:
                    self._try_cover_once()

    def _drop_connection(self):
        if self._aimp and self._recv:
            _send_timeout(self._aimp, WM_AIMP_COMMAND, CMD_UNREGISTER_NOTIFY, self._recv)
        if self._recv:
            _BY_HWND.pop(self._recv, None)
            user32.DestroyWindow(self._recv)
            self._recv = None
        if self._buf:
            kernel32.UnmapViewOfFile(self._buf)
            self._buf = None
        if self._mapping:
            kernel32.CloseHandle(self._mapping)  # 此前只 Unmap 不 Close：重连一次漏一个内核句柄
            self._mapping = None
        self._aimp = None
        with self._lock:
            self._snap["connected"] = False
            self._snap["state"] = STATE_NO_AIMP

    def _lose_aimp(self):
        """AIMP 探活超时（忙碌/退出中）：清连接状态并退消息泵，让 run() 重连。

        绝不能在消息回调里直接 _drop_connection()：销毁接收窗口后 GetMessageW
        永久阻塞，外层重连逻辑再也走不到——这是"偶发切歌不换壁纸、重启才恢复"
        的根因（AIMP 读大文件/卡顿超过 300ms 探活超时即触发）。
        """
        self._aimp = None
        with self._lock:
            self._snap["connected"] = False
            self._snap["state"] = STATE_NO_AIMP
        if self._recv:
            user32.PostMessageW(self._recv, 0x0012, 0, 0)  # WM_QUIT → 泵退出 → run() 重连

    def run(self):
        # 监护循环：任何一轮的意外异常（含 ctypes 原生层 OSError）都不允许弄死
        # 线程——线程一死 AIMP 连接就永久失效，壁纸再也不更新（只能重启程序）。
        while not self._stop_evt.is_set():
            try:
                self._run_once()
            except Exception:
                applog.log_exc("IPC 循环异常，重置连接:\n", *sys.exc_info())
                try:
                    self._drop_connection()
                except Exception:
                    pass
                self._stop_evt.wait(2.0)

    def _run_once(self):
        if self._connect():
            msg = wintypes.MSG()
            while not self._stop_evt.is_set():
                r = user32.GetMessageW(byref(msg), None, 0, 0)
                if r <= 0:
                    break
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
            self._drop_connection()
            if not self._stop_evt.is_set():
                self._stop_evt.wait(2.0)  # 探活失败刚退泵：AIMP 可能还在忙，别热循环重连
        else:
            with self._lock:
                self._snap["connected"] = False
                self._snap["state"] = STATE_NO_AIMP
            self._stop_evt.wait(5.0)
