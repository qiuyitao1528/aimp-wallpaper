# -*- coding: utf-8 -*-
"""给 fade.py 增加"确认桌面已换成新图再撤层"，避免过渡结束闪回旧图。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\fade.py"
s = io.open(P, encoding="utf-8").read()

if "def release_painted" in s:
    print("已存在")
    raise SystemExit

s = s.replace("def destroy_all(overlays) -> None:",
'''def _screen_pixel(x: int, y: int):
    """直接读屏像素（GetPixel，比 ImageGrab 快得多）。"""
    user32, gdi32 = desktop.user32, desktop.gdi32
    hdc = user32.GetDC(None)
    try:
        c = gdi32.GetPixel(hdc, int(x), int(y))
        if c == 0xFFFFFFFF:
            return None
        return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)
    finally:
        user32.ReleaseDC(None, hdc)


def release_painted(overlays, layers, timeout_ms: int = 1500) -> None:
    """撤掉覆盖层前，抽查桌面像素确认已是新壁纸；否则重新盖上再等。

    Windows 处理 SetWallpaper 后真正刷屏有 30~400ms 抖动，固定等待会在慢的时候
    闪回旧图（用户实测）。这里做"抽查-覆盖-重试"，最坏只漏一帧，感知不到。
    """
    if not overlays:
        return
    pts = []
    for x, y, w, h, img in layers:
        a = np.asarray(img.convert("RGB"))
        # 取几个避开边缘的采样点
        for fx, fy in ((0.25, 0.25), (0.5, 0.5), (0.75, 0.6)):
            px, py = int(w * fx), int(h * fy)
            pts.append((x + px, y + py, tuple(int(v) for v in a[py, px])))

    def matches() -> bool:
        hits = 0
        checked = 0
        for sx, sy, want in pts:
            got = _screen_pixel(sx, sy)
            if got is None:
                continue
            checked += 1
            if all(abs(got[i] - want[i]) <= 24 for i in range(3)):
                hits += 1
        return checked > 0 and hits >= max(1, checked * 2 // 3)

    try:
        for ov in overlays:
            ov.hide()
        end = time.perf_counter() + timeout_ms / 1000.0
        while time.perf_counter() < end:
            _pump(40)
            if matches():
                return  # 桌面已是新图，可以安全撤层
            for ov in overlays:  # 还没刷上，先盖回去避免闪回
                ov.show()
            _pump(120)
            for ov in overlays:
                ov.hide()
    finally:
        destroy_all(overlays)


def destroy_all(overlays) -> None:''')

# _Overlay 增加 hide/show
s = s.replace("    def destroy(self):",
'''    def hide(self) -> None:
        try:
            desktop.user32.ShowWindow(self.hwnd, SW_HIDE)
        except Exception:
            pass

    def show(self) -> None:
        try:
            desktop.user32.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
            self.set_alpha(self.alpha_max)
        except Exception:
            pass

    def destroy(self):''')

io.open(P, "w", encoding="utf-8").write(s)
print("fade.py: 已加 release_painted / hide / show")
