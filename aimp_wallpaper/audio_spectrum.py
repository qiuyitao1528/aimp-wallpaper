"""系统声音实时频谱（WASAPI 环回采集 + FFT，自绘面板数据源）。

AIMP 经典频谱的实现方式（据官方 apiVisuals.h / aimp2_sdk.h）：给可视化的数据
Spectrum[channel][256] 就是原始 FFT bin（线性频率轴），显示层直接画 bin——
没有对数分频。本模块对齐该实现：
- FFT 4096 点滑动窗（85ms，跟手）
- 线性频率轴：显示条按 bin 区间线性划分，每条取带内最大值
- dB 归一输出原始目标值（攻/衰包络由 UI 层按渲染帧率做，60fps 平滑不跳变）
"""
from __future__ import annotations

import threading

import numpy as np

BANDS = 48
N_FFT = 4096
F_MIN, F_MAX = 30.0, 16000.0  # 仅作占位，线性轴实际覆盖 0~Nyquist


class Spectrum(threading.Thread):
    def __init__(self, n_bands=BANDS, f_max=16000.0):
        super().__init__(daemon=True, name="spectrum")
        self._n = max(8, int(n_bands))
        self._f_max = float(f_max)
        self._lock = threading.Lock()
        self._bars = np.zeros(self._n)
        self._stop = threading.Event()
        self.err: str | None = None
        self._buf = np.zeros(0, dtype=np.float32)
        self._win = np.hanning(N_FFT).astype(np.float32)  # 只算一次
        self._bin_idx = None  # 每条显示条对应的 bin 区间边界，打开设备后计算
        self._sr = 48000
        self._channels = 2

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return self._bars.copy()

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
                self._bars = norm  # 原始目标值；攻/衰包络由 UI 层按帧率做（平滑不跳变）
        except Exception:
            pass
        return (None, pyaudio.paContinue)

    def run(self):
        import pyaudiowpatch as pyaudio
        try:
            p = pyaudio.PyAudio()
            dev = p.get_default_wasapi_loopback()
            self._channels = max(1, int(dev.get("maxInputChannels", 2)))
            self._sr = int(dev.get("defaultSampleRate", 48000))
            self._compute_bins()
            stream = p.open(format=pyaudio.paFloat32,
                            channels=self._channels,
                            rate=self._sr,
                            input=True,
                            input_device_index=dev["index"],
                            frames_per_buffer=2048,
                            stream_callback=self._callback)
            stream.start_stream()
            while not self._stop.is_set() and stream.is_active():
                self._stop.wait(0.2)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            self.err = str(e)
            with self._lock:
                self._bars = np.full(self._n, -1.0)  # UI 显示失败提示
