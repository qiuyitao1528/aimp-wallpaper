"""系统声音实时频谱（WASAPI 环回采集 + FFT，自绘面板数据源）。

AIMP 经典频谱的实现方式（据官方 apiVisuals.h / aimp2_sdk.h）：给可视化的数据
Spectrum[channel][256] 就是原始 FFT bin（线性频率轴），显示层直接画 bin——
没有对数分频。本模块对齐该实现：
- FFT 4096 点滑动窗（85ms，跟手）
- 线性频率轴：显示条按 bin 区间线性划分，每条取带内最大值
- dB 归一输出原始目标值（攻/衰包络由 UI 层按渲染帧率做，60fps 平滑不跳变）
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import POINTER, byref, c_void_p

import numpy as np

_ole32 = ctypes.WinDLL("ole32", use_last_error=True)
_ole32.CoTaskMemFree.argtypes = [c_void_p]

BANDS = 48
N_FFT = 4096
F_MIN, F_MAX = 30.0, 16000.0  # 仅作占位，线性轴实际覆盖 0~Nyquist

# Core Audio：默认渲染设备直查（用于检测系统默认输出设备切换）
_IMMDEV_CLSID = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"  # MMDeviceEnumerator
_IMMENUM_IID = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
_ole32 = ctypes.WinDLL("ole32", use_last_error=True)

_HRESULT = ctypes.HRESULT


def _com_release(ptr) -> None:
    """释放 COM 对象（vtable 第 3 槽 = Release），失败忽略。"""
    try:
        vtbl_ptr = ctypes.cast(ptr, POINTER(c_void_p)).contents.value
        vtbl = ctypes.cast(vtbl_ptr, POINTER(c_void_p))
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vtbl[2])
        release(ptr)
    except Exception:
        pass


def _default_endpoint_id() -> str | None:
    """当前默认渲染设备 ID（Core Audio 直查，微秒级，不开设备）。失败返回 None。

    关键点：系统切换默认输出设备后，旧设备的 loopback 流仍处于 active 状态
    （只是再也收不到声音），靠 is_active() 检测不到——必须比对外设 ID 主动重建。
    走手写 vtable 直调（与 _com_release 同款），避开 comtypes 接口封装。
    """
    try:
        import comtypes
        from comtypes import GUID, POINTER

        comtypes.CoInitialize()
        ppv = c_void_p()
        hr = _ole32.CoCreateInstance(byref(GUID(_IMMDEV_CLSID)), None, 1,  # CLSCTX_INPROC_SERVER
                                     byref(GUID(_IMMENUM_IID)), byref(ppv))
        if hr != 0 or not ppv.value:
            return None
        try:
            enum_vtbl = ctypes.cast(ctypes.cast(ppv.value, POINTER(c_void_p)).contents.value,
                                    POINTER(c_void_p))
            # IMMDeviceEnumerator 槽位 4 = GetDefaultAudioEndpoint(flow, role, &dev)
            get_default = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, ctypes.c_uint,
                                             ctypes.c_uint, c_void_p)(enum_vtbl[4])
            dev = c_void_p()
            if get_default(ppv.value, 0, 1, byref(dev)) != 0 or not dev.value:
                return None
            try:
                dev_vtbl = ctypes.cast(ctypes.cast(dev.value, POINTER(c_void_p)).contents.value,
                                       POINTER(c_void_p))
                # IMMDevice 槽位 5 = GetId(&pszId)
                get_id = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, c_void_p)(dev_vtbl[5])
                id_ptr = c_void_p()
                hr = get_id(dev.value, byref(id_ptr))
                if hr != 0 or not id_ptr.value:
                    return None
                try:
                    return ctypes.wstring_at(id_ptr.value) or None
                finally:
                    _ole32.CoTaskMemFree(id_ptr)
            finally:
                _com_release(dev)
        finally:
            _com_release(ppv)
    except Exception:
        return None


class Spectrum(threading.Thread):
    def __init__(self, n_bands=BANDS, f_max=16000.0):
        super().__init__(daemon=True, name="spectrum")
        self._n = max(8, int(n_bands))
        self._f_max = float(f_max)
        self._lock = threading.Lock()
        self._bars = np.zeros(self._n)
        self._stop = threading.Event()
        self._paused = threading.Event()  # 面板隐藏时挂起采集（活动音频流阻止显示器睡眠）
        self.err: str | None = None
        self._buf = np.zeros(0, dtype=np.float32)
        self._win = np.hanning(N_FFT).astype(np.float32)  # 只算一次
        self._bin_idx = None  # 每条显示条对应的 bin 区间边界，打开设备后计算
        self._sr = 48000
        self._channels = 2
        self._prev_bars = np.zeros(self._n)  # 上一代目标（供 UI 时间插值）
        self._t_prev = 0.0
        self._t_curr = 0.0

    def pause(self):
        """挂起采集：关闭流，让系统可以正常睡眠/省电。"""
        self._paused.set()

    def resume(self):
        """恢复采集（下次循环重建流，自动跟随当前默认设备）。"""
        self._paused.clear()

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return self._bars.copy()

    def interp_snapshot(self) -> tuple[np.ndarray, np.ndarray, float, float]:
        """返回 (当前目标, 上一目标, t_prev, t_curr)，供 UI 做时间线性插值。"""
        with self._lock:
            return self._bars.copy(), self._prev_bars.copy(), self._t_prev, self._t_curr

    def stop(self):
        self._stop.set()

    def _compute_bins(self):
        hi_bin = min(N_FFT // 2, max(16, int(self._f_max / self._sr * N_FFT)))
        idx = np.linspace(1, hi_bin, self._n + 1).astype(int)
        idx = np.maximum.accumulate(idx)
        self._bin_idx = idx

    def _callback(self, in_data, frame_count, _time, _status):
        import pyaudiowpatch as pyaudio
        try:
            mono = np.frombuffer(in_data, np.float32)
            if self._channels > 1:
                mono = mono.reshape(-1, self._channels).mean(axis=1)
            self._buf = np.concatenate([self._buf, mono])[-N_FFT:]
            if len(self._buf) < N_FFT:
                return (None, pyaudio.paContinue)
            spec = np.abs(np.fft.rfft(self._buf * self._win)) / (N_FFT / 2)
            hi = int(self._bin_idx[-1])
            # 分频取 max 向量化（reduceat）；最后一组到 hi_bin 截止，与线性分轴语义一致
            vals = np.maximum.reduceat(spec[:hi], np.minimum(self._bin_idx[:-1], hi - 1))
            db = 20 * np.log10(vals + 1e-10)
            norm = np.clip((db + 78) / 50.0, 0.0, 1.0)
            with self._lock:
                self._prev_bars = self._bars
                self._bars = norm  # 原始目标值；攻/衰包络由 UI 层按帧率做（平滑不跳变）
                self._t_prev = self._t_curr if self._t_curr else time.monotonic() - 0.0428
                self._t_curr = time.monotonic()
        except Exception:
            pass
        return (None, pyaudio.paContinue)

    def run(self):
        """采集主循环：默认输出设备切换/流失效后自动重建跟随新设备；面板隐藏时
        挂起（关闭流让系统正常睡眠），恢复后重建流。

        设备切换后旧设备的 loopback 流仍为 active（只是收不到声音），靠
        is_active() 检测不到——每 ~2s 比对默认设备 ID，变了就重建流。
        此前流一失效线程就静默退出，频谱从此冻结；错误路径也没有 terminate，
        泄漏 WASAPI/COM 资源。两条都在这一版修掉。
        """
        import pyaudiowpatch as pyaudio
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        current_id = None
        poll_n = 0
        while not self._stop.is_set():
            if self._paused.is_set():
                self._stop.wait(0.5)  # 挂起态：不开设备
                continue
            p = None
            stream = None
            try:
                p = pyaudio.PyAudio()
                dev = p.get_default_wasapi_loopback()
                self._channels = max(1, int(dev.get("maxInputChannels", 2)))
                self._sr = int(dev.get("defaultSampleRate", 48000))
                self._compute_bins()
                current_id = _default_endpoint_id()
                stream = p.open(format=pyaudio.paFloat32,
                                channels=self._channels,
                                rate=self._sr,
                                input=True,
                                input_device_index=dev["index"],
                                frames_per_buffer=2048,
                                stream_callback=self._callback)
                stream.start_stream()
                self.err = None
                while not self._stop.is_set() and not self._paused.is_set() and stream.is_active():
                    self._stop.wait(0.2)
                    poll_n += 1
                    if poll_n % 10 == 0:  # ~2s 一次：默认输出设备切换 → 重建流
                        now_id = _default_endpoint_id()
                        if now_id and current_id and now_id != current_id:
                            break
            except Exception as e:
                self.err = str(e)
                with self._lock:
                    self._prev_bars = self._bars = np.full(self._n, -1.0)  # UI 显示失败提示
                    self._t_prev = self._t_curr = time.monotonic()
            finally:
                try:
                    if stream is not None:
                        stream.stop_stream()
                        stream.close()
                except Exception:
                    pass
                try:
                    if p is not None:
                        p.terminate()  # 此前错误路径不 terminate，泄漏 COM 资源
                except Exception:
                    pass
            if not self._stop.is_set() and not self._paused.is_set():
                self._stop.wait(2.0)  # 设备恢复/切换后自动跟随
