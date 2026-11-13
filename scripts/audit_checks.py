# -*- coding: utf-8 -*-
"""深度审计实测脚本：29 项带编号检查（bug 复现口径 + 修复后行为断言）。

覆盖 2026-11-13 审计发现的全部修复项 + 关键回归护栏。离线可跑：
- 不碰桌面壁纸（COM 用 FakeDW 假对象）
- 音频用假 pyaudiowpatch 模块注入
- 配置/缓存/歌词全部走临时目录
"""
import ast
import ctypes
import hashlib
import json
import os
import sys
import tempfile
import time
import types

sys.path.insert(0, ".")
TMP = tempfile.mkdtemp(prefix="aimpwp_audit_")

from aimp_wallpaper import config, desktop, wallpaper  # noqa: E402
import aimp_wallpaper.lyrics as ly  # noqa: E402

CHECKS = []


def check(n, title, fn):
    try:
        fn()
        CHECKS.append((n, title, True, ""))
        print(f"[PASS] #{n:02d} {title}")
    except Exception as e:
        CHECKS.append((n, title, False, str(e)))
        print(f"[FAIL] #{n:02d} {title}  ->  {e}")


def func_ast(path, name):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def flac_block(btype, data, last=False):
    return bytes([(0x80 if last else 0) | btype]) + len(data).to_bytes(3, "big") + data


def vorbis_comment(comments):
    vendor = b"audit"
    out = len(vendor).to_bytes(4, "little") + vendor + len(comments).to_bytes(4, "little")
    for k, v in comments:
        item = k.encode() + b"=" + v.encode()
        out += len(item).to_bytes(4, "little") + item
    return out


# ---- 1 面板监视器：after 无条件重排（此前首轮 return 即断链，监视器形同虚设） ----
def c01():
    node = func_ast("aimp_wallpaper/__main__.py", "_watch_panel")
    assert node is not None, "_watch_panel 不存在"
    last = node.body[-1]
    assert isinstance(last, ast.Expr) and "after" in ast.dump(last), "末句不是 root.after 重排"
    assert isinstance(node.body[0], ast.Try), "主体应有 try/except 防护"


# ---- 2 托盘开关不触发重建（按建面板时宽高对比，重现走 deiconify） ----
def c02():
    node = func_ast("aimp_wallpaper/__main__.py", "_watch_panel")
    dump = ast.dump(node)
    assert "'built'" in dump, "未按建面板时尺寸对比（托盘开关会被误重建）"
    assert "deiconify" in dump, "缺重现不重建路径"
    assert "withdraw" in dump


# ---- 3 歌词缓存键含语言偏好（此前简/繁切换对已抓过的歌永远无效） ----
def c03():
    d = os.path.join(TMP, "c03")
    os.makedirs(d, exist_ok=True)
    audio = os.path.join(d, "song.mp3")
    open(audio, "w").write("x")
    open(os.path.join(d, "song.lrc"), "w", encoding="utf-8").write("[01:00.00]hello world")
    a = ly.fetch_lrc("T3", "A3", 60000, d, audio, "zh-Hans")
    b = ly.fetch_lrc("T3", "A3", 60000, d, audio, "zh-Hant")
    assert a and b, "歌词没抓到"
    files = [f for f in os.listdir(d) if f.endswith(".lrc") and f != "song.lrc"]
    assert len(files) == 2, f"两种偏好应产生两份缓存，实际 {files}"


# ---- 3b 抓取线程按语言偏好重抓（此前 key 不含 pref，切语言当前歌不重抓） ----
def c03b():
    calls = []
    orig = ly.fetch_lrc
    cfg = {"output_dir": os.path.join(TMP, "c03b"), "lyrics_lang_pref": "zh-Hans"}
    os.makedirs(cfg["output_dir"], exist_ok=True)

    def fake_fetch(title, artist, dur, cache_dir, audio_path=None, lang_pref="zh-Hans"):
        calls.append(lang_pref)
        if len(calls) == 1:
            cfg["lyrics_lang_pref"] = "zh-Hant"  # 第一次抓完模拟用户切换偏好
        return None

    ly.fetch_lrc = fake_fetch
    try:
        class FakeIPC:
            def snapshot(self):
                return {"connected": True, "title": "T", "artist": "A",
                        "filename": "", "duration_ms": 0}

        class FakeStop:
            seq = iter([False, False, True])

            def wait(self, t=None):
                return next(self.seq)

        f = ly.LyricsFetcher(FakeIPC(), cfg, lambda lines: None)
        f._stop = FakeStop()
        f.run()  # 直接同步跑一轮循环
        assert calls == ["zh-Hans", "zh-Hant"], f"应按语言切换重抓，实际 {calls}"
    finally:
        ly.fetch_lrc = orig


# ---- 4 壁纸槽位按"轮次+屏序号"交替（此前全局交替→双屏每轮覆写正被引用的文件） ----
def c04():
    wallpaper._SLOT["n"] = 0
    seq0, seq1 = [], []
    for _ in range(4):
        wallpaper._SLOT["n"] += 1
        seq0.append(wallpaper._slot_for(0))
        seq1.append(wallpaper._slot_for(1))
    assert seq0 == ["B", "A", "B", "A"], f"屏0 应交替，实际 {seq0}"
    assert seq1 == ["A", "B", "A", "B"], f"屏1 应反向交替，实际 {seq1}"
    assert seq0[0] != seq1[0], "同轮两屏应不同槽位"


# ---- 5 关文字总开关后删除陈旧 vis_anchor.json（此前面板/歌词钉在消失的文字区） ----
def c05():
    d = os.path.join(TMP, "c05")
    os.makedirs(d, exist_ok=True)
    stale = os.path.join(d, "vis_anchor.json")
    json.dump({"x": 100, "y": 100}, open(stale, "w"))

    class FakeDW:
        def SetWallpaper(self, mid, path):
            return None

        def GetPosition(self):
            return 4  # DWPOS_FILL

        def SetPosition(self, p):
            return None

    orig = wallpaper._get_wallpaper_com
    wallpaper._get_wallpaper_com = lambda: FakeDW()
    try:
        cfg = dict(config.DEFAULTS)
        cfg.update({"output_dir": d, "fade_native": False, "show_text": False})
        monitors = [{"id": "MONO", "w": 640, "h": 480, "left": 0, "top": 0}]
        wallpaper.render_and_apply(None, {"title": "t", "artist": "a", "album": ""},
                                   cfg, monitors)
        assert not os.path.exists(stale), "无锚点时陈旧 vis_anchor.json 应被删除"
    finally:
        wallpaper._get_wallpaper_com = orig


# ---- 6 频谱 _frame 整帧防护（此前一帧异常断 after 链，面板永久冻结） ----
def c06():
    node = func_ast("aimp_wallpaper/vis_panel.py", "_frame")
    dump = ast.dump(node)
    assert any(isinstance(s, ast.Try) for s in node.body), "_frame 应整体 try/except"
    assert "_frame_inner" in dump, "帧体应拆到 _frame_inner"
    last = node.body[-1]
    assert isinstance(last, ast.Expr) and "after" in ast.dump(last), "重排应在防护之外无条件执行"


# ---- 7 覆盖窗位置钳制用虚拟桌面（此前 work_area 只含主屏，副屏面板被拽回主屏） ----
def c07():
    node = func_ast("aimp_wallpaper/lyrics.py", "_auto_pos")
    assert "virtual_screen" in ast.dump(node), "歌词 _auto_pos 未用虚拟屏钳制"
    node2 = func_ast("aimp_wallpaper/vis_panel.py", "_auto_pos")
    assert "virtual_screen" in ast.dump(node2), "面板 _auto_pos 未用虚拟屏钳制"
    vx = desktop.virtual_screen()
    assert vx[2] > vx[0] and vx[3] > vx[1], f"虚拟屏尺寸异常 {vx}"


# ---- 8 配置原子写（此前写一半崩溃 → 全部设置静默回默认） ----
def c08():
    p = os.path.join(TMP, "c08.json")
    config.CONFIG_PATH = p
    cfg = dict(config.DEFAULTS)
    cfg["title_color"] = "#123456"
    config.save(cfg)
    assert json.load(open(p, encoding="utf-8"))["title_color"] == "#123456"
    # 模拟写一半崩：dump 后抛异常 → 旧文件必须完好
    real_dump = json.dump

    def boom(obj, fp, *a, **k):
        real_dump(obj, fp, *a, **k)
        raise OSError("disk full")

    json.dump = boom
    try:
        try:
            cfg["title_color"] = "#ABCDEF"
            config.save(cfg)
        except OSError:
            pass
        assert json.load(open(p, encoding="utf-8"))["title_color"] == "#123456", \
            "写入中断不应损坏既有配置"
    finally:
        json.dump = real_dump


# ---- 9/10 频谱：流失效自动重建跟随新设备 + 错误路径也 terminate（此前线程退出=永久冻结） ----
class FakeStream:
    def is_active(self):
        return False  # 立即失效 → 触发重建循环

    def start_stream(self):
        return None

    def stop_stream(self):
        return None

    def close(self):
        return None


def c09_10():
    class FakePy:
        count = 0
        opened = 0
        terminates = 0

        def __init__(self):
            FakePy.count += 1

        def get_default_wasapi_loopback(self):
            return {"index": 0, "maxInputChannels": 2, "defaultSampleRate": 48000}

        def open(self, **kw):
            FakePy.opened += 1
            if FakePy.opened == 1:
                raise RuntimeError("device gone")  # 第一次打开失败：错误路径也要 terminate
            return FakeStream()

        def terminate(self):
            FakePy.terminates += 1

    fake_mod = types.SimpleNamespace(PyAudio=FakePy, paFloat32=1, paContinue=0)
    sys.modules["pyaudiowpatch"] = fake_mod
    from aimp_wallpaper.audio_spectrum import Spectrum

    class FakeStop:
        n = 0
        limit = 3

        def is_set(self):
            return self.n >= self.limit

        def wait(self, t=None):
            self.n += 1
            return True

    sp = Spectrum(n_bands=16)
    sp._stop = FakeStop()
    sp.run()  # 同线程直跑 3 轮：失败→重建→失效→重建
    assert FakePy.count >= 2, f"流失效应重建，实际只建了 {FakePy.count} 次"
    assert FakePy.terminates == FakePy.count, \
        f"每次 PyAudio 都应 terminate（含错误路径）：{FakePy.terminates}/{FakePy.count}"
    assert sp.err is None, "重建成功后 err 应清空"


# ---- 11 OverlaySurface 释放不漏 GDI 对象（此前面板重建每次漏 DIB+DC） ----
def c11():
    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    u32.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    u32.GetGuiResources.restype = ctypes.c_uint
    proc = k32.GetCurrentProcess()
    from aimp_wallpaper.desktop import OverlaySurface
    base = u32.GetGuiResources(proc, 0)
    surfs = []
    peak = base
    try:
        for _ in range(3):
            surfs.append(OverlaySurface(1, 300, 200))
        assert all(s.ok for s in surfs), "OverlaySurface 创建失败"
        peak = u32.GetGuiResources(proc, 0)
        assert peak - base >= 6, f"测试前提：每张表面应占用 2+ GDI 对象（base={base} peak={peak}）"
    finally:
        for s in surfs:
            s.close()
    time.sleep(0.2)
    after = u32.GetGuiResources(proc, 0)
    assert after <= base + 2, f"GDI 对象未释放：base={base} peak={peak} after={after}"


# ---- 12 _wrap_title 死参数 line_limit 已删，输出不变量"每行 ≤ max_w"成立 ----
def c12():
    from PIL import Image, ImageDraw
    node = func_ast("aimp_wallpaper/wallpaper.py", "_wrap_title")
    params = [a.arg for a in node.args.args]
    assert "line_limit" not in params, "line_limit 死参数应已移除"
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = wallpaper._load_font(False, 24, None)[0]
    for text in ("A" * 120, "alpha beta gamma delta epsilon zeta", "中文长标题没有空格" * 6):
        lines = wallpaper._wrap_title(d, text, font, 260, 4, 0)
        for ln in lines:
            w = wallpaper._text_len(d, ln, font)
            assert w <= 260, f"折行输出超过 max_w：{w:.0f}px（{ln[:20]}…）"


# ---- 13 歌词右键菜单锁定勾选随设置同步（此前菜单显示陈旧状态） ----
def c13():
    node = func_ast("aimp_wallpaper/lyrics.py", "_tick")
    assert "_lock_var" in ast.dump(node), "_tick 应同步 _lock_var（右键菜单勾选）"
    node2 = func_ast("aimp_wallpaper/vis_panel.py", "_frame_inner")
    assert "_lock_var" in ast.dump(node2), "面板帧维护应同步 _lock_var"


# ---- 14 ID3v2.2 的 ULT 帧也能读（此前只扫 10 字节头，老文件歌词永远找不到） ----
def c14():
    body_body = bytes([1]) + b"eng" + b"\x00\x00" + "歌词测试内容".encode("utf-16")
    frame = b"ULT" + len(body_body).to_bytes(3, "big") + body_body
    size = len(frame)
    tag = b"ID3" + bytes([2, 0, 0]) + bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F,
                                             (size >> 7) & 0x7F, size & 0x7F]) + frame
    p = os.path.join(TMP, "c14.mp3")
    open(p, "wb").write(tag + b"\x00" * 16)
    with open(p, "rb") as f:
        text = ly._read_id3_lyrics(f)
    assert text == "歌词测试内容", f"ID3v2.2 ULT 应能读取，实际 {text!r}"


# ---- 15 FLAC 扫全部 COMMENT 块（此前只看第一块，写在后面的歌词读不到） ----
def c15():
    p = os.path.join(TMP, "c15.flac")
    data = (b"fLaC"
            + flac_block(0, b"\x00" * 34)
            + flac_block(4, vorbis_comment([("TITLE", "x")]))
            + flac_block(4, vorbis_comment([("LYRICS", "[01:00.00]simp line")]), last=True))
    open(p, "wb").write(data)
    got = ly._read_embedded_lyrics(p)
    assert got and "simp line" in got, f"第二个 COMMENT 块的歌词应被读到，实际 {got!r}"
    # 双版本择优：简体优先不应选中繁体块
    trad = "我們這個來說時會後點發現現實對從還經過為與藝術"
    p2 = os.path.join(TMP, "c15b.flac")
    data2 = (b"fLaC"
             + flac_block(0, b"\x00" * 34)
             + flac_block(4, vorbis_comment([("LYRICS", f"[01:00.00]{trad}")]))
             + flac_block(4, vorbis_comment([("LYRICS", "[01:00.00]简体行")]), last=True))
    open(p2, "wb").write(data2)
    got2 = ly._read_embedded_lyrics(p2, "zh-Hans")
    assert got2 and "简体行" in got2, f"简体优先应选简体块，实际 {got2!r}"


# ---- 16 同时间戳重复行不再被当翻译吞掉（副歌回声此前直接消失） ----
def c16():
    orig = ly.parse_lrc("[01:00.00]chorus\n[01:00.00]chorus")
    paired = ly._pair_lyrics(orig)
    texts = [t for _ms, t, _tr in paired]
    assert texts.count("chorus") == 2, f"重复行应保留两条，实际 {paired}"
    # 正常双语对照仍配对
    bi = ly.parse_lrc("[01:00.00]你好\n[01:00.00]hello")
    paired2 = ly._pair_lyrics(bi)
    assert len(paired2) == 1 and paired2[0][2] == "hello", "双语行应配对为翻译"


# ---- 17 缓存命中不回写磁盘（此前每首歌每轮重复写缓存并抹掉原始 LRC） ----
def c17():
    d = os.path.join(TMP, "c17")
    os.makedirs(d, exist_ok=True)
    key = hashlib.md5("t17|a17|zh-Hans".encode()).hexdigest()
    cache_file = os.path.join(d, key + ".lrc")
    open(cache_file, "w", encoding="utf-8").write("[00:59.000]cached line")
    m1 = os.path.getmtime(cache_file)
    time.sleep(0.05)
    got = ly.fetch_lrc("t17", "a17", 60000, d, None, "zh-Hans")
    assert got and got[0][1] == "cached line", "缓存内容应被读到"
    assert os.path.getmtime(cache_file) == m1, "缓存命中不应回写文件"
    # 未命中（同目录 .lrc）仍回写规范化缓存
    audio = os.path.join(d, "s17.mp3")
    open(audio, "w").write("x")
    open(os.path.join(d, "s17.lrc"), "w", encoding="utf-8").write("[01:00.00]fresh line")
    got2 = ly.fetch_lrc("s17", "a17", 60000, d, audio, "zh-Hans")
    assert got2 and got2[0][1] == "fresh line"
    assert any(f.endswith(".lrc") and "s17" not in f for f in os.listdir(d)), "新歌应回写缓存"


# ---- 18 fetch_lrc 文件句柄全部 with 关闭（代码级：无裸 open().read()） ----
def c18():
    import re
    src = open("aimp_wallpaper/lyrics.py", encoding="utf-8").read()
    assert not re.search(r"open\([^)]*\)\.read\(\)", src), "存在未 with 的 open().read()"


# ---- 20 过时注释已修（lyrics_width 曾标注"重启生效"，实测实时生效） ----
def c20():
    src = open("aimp_wallpaper/config.py", encoding="utf-8").read()
    assert "重启生效" not in src, "config.py 仍有过时的「重启生效」注释"


# ---- 22 parse_lrc：offset / 多时间戳 / 词级标签剥离（回归护栏） ----
def c22():
    lines = ly.parse_lrc("[offset:500]\n[01:01.50][01:02]hello <00:01.0>world")
    assert len(lines) == 2, f"一行双时间戳应出两条，实际 {lines}"
    assert lines[0][0] == 62000 and lines[1][0] == 62500, f"offset 应加到时间戳：{lines}"
    assert lines[0][1] == "hello world", f"词级标签应剥离：{lines[0][1]!r}"


# ---- 23 _format_info：缺失项整段省略（回归护栏） ----
def c23():
    cfg = dict(config.DEFAULTS)
    empty = wallpaper._format_info(cfg, {"filename": "", "duration_ms": 0})
    assert empty == "", f"全缺失应返回空串（整行隐藏），实际 {empty!r}"
    flac = wallpaper._format_info(cfg, {"filename": "x.flac"})
    assert flac == "FLAC", f"只有格式已知时应只剩 FLAC，实际 {flac!r}"


# ---- 24 空格断行：断点前移到空格之后、单词不被切开（回归护栏） ----
def c24():
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = wallpaper._load_font(False, 24, None)[0]
    text = "alpha beta gamma delta"
    lines = wallpaper._wrap_title(d, text, font, wallpaper._text_len(d, "alpha beta", font),
                                  3, 8)
    words = text.split()
    for ln in lines:
        for w in ln.split():
            assert w in words, f"单词被切开：{ln!r}"


# ---- 25 无封面占位渲染（回归护栏：占位框 + 音符符号，不碰 COM） ----
def c25():
    cfg = dict(config.DEFAULTS)
    img = wallpaper.render_poster(None, {"title": "t", "artist": "a", "album": ""},
                                  640, 480, cfg)
    assert img.size == (640, 480)


# ---- 25 FLAC 头解析补位深/采样率（回归护栏） ----
def c26():
    si = bytearray(34)
    si[10], si[11], si[12], si[13] = 0x0B, 0xB8, 0x00, 0xF0  # 48kHz / 16bit
    data = b"fLaC" + flac_block(0, bytes(si))
    p = os.path.join(TMP, "c26.flac")
    open(p, "wb").write(data)
    vals = wallpaper._audio_info(p, 180000, 0, 0, 0)
    assert vals["samplerate"] == "48 kHz", f"采样率解析错：{vals}"
    assert vals["bits"] == "16 bit", f"位深解析错：{vals}"


# ---- 26 旧配置迁移：sub_* 播种 artist_*/album_*（回归护栏） ----
def c27():
    cfg = dict(config.DEFAULTS)
    data = {"sub_size_ratio": 0.05, "sub_color": "#FF0000"}
    cfg.update(data)  # 与 load() 一致：先合并用户数据再迁移
    config._migrate(cfg, data)
    assert cfg["artist_size_ratio"] == 0.05 and cfg["album_size_ratio"] == 0.05
    assert cfg["artist_color"] == "#FF0000" and cfg["album_color"] == "#FF0000"


# ---- 28 非法颜色回退（回归护栏） ----
def c28():
    assert wallpaper._hex_rgb("#GGGGGG", (1, 2, 3)) == (1, 2, 3)
    assert wallpaper._hex_rgb(None, (1, 2, 3)) == (1, 2, 3)
    assert wallpaper._hex_rgb("#FF0000", (1, 2, 3)) == (255, 0, 0)


# ---- 29 省略号收敛（回归护栏） ----
def c29():
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = wallpaper._load_font(False, 24, None)[0]
    out = wallpaper._ellipsis(d, "很长的一段文本" * 20, font, 200)
    assert wallpaper._text_len(d, out, font) <= 200 + 2, "省略号后应收敛到限宽内"
    assert out.endswith("…")


# ---- 30 配置往返（回归护栏） ----
def c30():
    p = os.path.join(TMP, "c30.json")
    config.CONFIG_PATH = p
    cfg = dict(config.DEFAULTS)
    cfg.update({"title_color": "#00FF00", "vis_width": 500,
                "line_order": ["album", "title", "artist", "info"]})
    config.save(cfg)
    loaded = config.load()
    assert loaded["title_color"] == "#00FF00" and loaded["vis_width"] == 500
    assert loaded["line_order"][0] == "album"


for n, title, fn in [
    (1, "面板监视器 after 无条件重排（此前首轮即断链）", c01),
    (2, "托盘开关面板不触发无谓重建", c02),
    (3, "歌词缓存键含语言偏好", c03),
    (4, "歌词抓取线程按语言切换重抓", c03b),
    (5, "壁纸槽位每屏独立交替", c04),
    (6, "关文字后删除陈旧 vis_anchor.json", c05),
    (7, "频谱 _frame 整帧防护不断链", c06),
    (8, "覆盖窗钳制用虚拟桌面（多屏）", c07),
    (9, "配置原子写（中断不损坏）", c08),
    (10, "频谱流失效自动重建", c09_10),
    (11, "频谱错误路径 PyAudio 必 terminate", c09_10),
    (12, "OverlaySurface 释放不漏 GDI 对象", c11),
    (13, "line_limit 硬上限真生效（长词不出屏）", c12),
    (14, "歌词/面板锁定菜单随设置同步", c13),
    (15, "ID3v2.2 ULT 歌词可读", c14),
    (16, "FLAC 全部 COMMENT 块扫描+简繁择优", c15),
    (17, "同时间戳重复行不当翻译吞掉", c16),
    (18, "缓存命中不回写磁盘", c17),
    (19, "歌词文件句柄全部 with 关闭", c18),
    (20, "config.py 过时注释已修", c20),
    (21, "parse_lrc offset/多标签/词级标签", c22),
    (22, "歌曲信息缺失项整段省略", c23),
    (23, "空格断行不切词", c24),
    (24, "无封面占位渲染", c25),
    (25, "FLAC 头解析采样率/位深", c26),
    (26, "旧配置 sub_* 迁移", c27),
    (27, "非法颜色回退", c28),
    (28, "省略号宽度收敛", c29),
    (29, "配置保存/加载往返", c30),
]:
    check(n, title, fn)

fails = [c for c in CHECKS if not c[2]]
print(f"\n总计 {len(CHECKS)} 项，通过 {len(CHECKS) - len(fails)}，失败 {len(fails)}")
sys.exit(1 if fails else 0)
