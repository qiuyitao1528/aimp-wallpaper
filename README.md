<div align="center">

# AIMP Wallpaper

**AIMP 专辑封面动态壁纸工具**

基于 AIMP 自带 Remote API，将正在播放曲目的封面与元数据实时渲染为海报式桌面壁纸，附带经典频谱可视化面板与桌面歌词。无需安装任何 AIMP 插件，支持 Windows 10 / 11。

[![Release](https://img.shields.io/github/v/release/qiuyitao1528/aimp-wallpaper?style=flat-square&color=4C8BF5)](https://github.com/qiuyitao1528/aimp-wallpaper/releases/latest)
[![Pre-release](https://img.shields.io/badge/pre--release-0.9.0--beta.1-FB8C00?style=flat-square)](https://github.com/qiuyitao1528/aimp-wallpaper/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6?style=flat-square&logo=windows)](https://github.com/qiuyitao1528/aimp-wallpaper)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/qiuyitao1528/aimp-wallpaper?style=flat-square&color=3DA639)](LICENSE)
[![AIMP](https://img.shields.io/badge/AIMP-v5.40%20tested-FF6B35?style=flat-square)](https://www.aimp.ru/)

[功能特性](#-功能特性) · [安装](#-安装) · [快速开始](#-快速开始) · [配置说明](#-配置说明) · [常见问题](#-常见问题) · [从源码构建](#-从源码构建)

</div>

---

<div align="center">
<img src="docs/screenshot.png" width="880" alt="AIMP Wallpaper 效果预览">
</div>

---

## ✨ 功能特性

| | 特性 | 说明 |
|---|---|---|
| 🖼️ | **海报式壁纸** | 切歌自动更新：封面 1:1 居左（不放大、不裁剪），右侧渲染歌名/歌手/专辑/歌曲信息四行文字 |
| 🎨 | **逐行排版精调** | 四行各自独立：字号、字体、颜色、加粗、阴影、描边、折行规则（按宽度/空格断行）；支持单独隐藏与自由排序 |
| 🌄 | **多种背景方案** | 模糊 / 模糊+暗角 / 原图铺满 / 主色渐变；模糊提供高斯、柔焦、雾面、辉光四种变体 |
| 🌙 | **日/夜主题跟随** | 跟随 Windows 深浅色模式，夜间自动叠加遮罩，实时切换 |
| ℹ️ | **歌曲信息行** | 音频格式、采样率、比特率、位深（自文件头解析），展示模板可定制 |
| 🎤 | **桌面歌词** | 原文/译文对照悬浮窗；歌词来源为本地缓存、歌曲同目录 `.lrc` 与网易云在线查询 |
| ⏸️ | **暂停反馈** | 暂停时压暗（范围可选）、显示角标或缩小封面，可自由组合 |
| 📊 | **频谱面板** | AIMP 经典样式，基于 WASAPI 环回自算 FFT，刷新率 10~120fps 可调 |
| 🖥️ | **系统集成** | 多显示器逐屏渲染、系统托盘、原壁纸记录与恢复、`UpdateLayeredWindow` 低占用呈现 |

---

## 📦 安装

**系统要求**：Windows 10 / 11（64 位）、[AIMP](https://www.aimp.ru/) v5.40（实测版本）

从 [Releases](https://github.com/qiuyitao1528/aimp-wallpaper/releases/latest) 下载，两种发行形式任选：

| 形式 | 文件 | 特点 |
|---|---|---|
| 安装版 | `aimp-wallpaper-vX.Y.Z[-tag]-setup.exe` | 免管理员安装至当前用户，含开始菜单快捷方式，支持卸载时自动恢复原壁纸 |
| 绿色版 | `aimp-wallpaper-vX.Y.Z-win64.zip` | 解压即用，不写注册表，配置随目录保存，适合便携使用 |

---

## 🚀 快速开始

1. 启动 AIMP Wallpaper（首次运行自动记录当前原壁纸，用于退出时恢复）
2. 在 AIMP 中播放任意曲目，壁纸随即更新为该曲目的海报
3. 通过系统托盘图标或频谱面板右键菜单进行设置与调整

**托盘菜单**：设置 · 频谱面板 · 桌面歌词 · 恢复原壁纸 · 退出
**手动恢复壁纸**：`aimp-wallpaper.exe restore`

---

## ⚙️ 配置说明

设置窗口共八页，所有配置保存后立即生效（无需重启程序）：

| 页签 | 内容 |
|---|---|
| **壁纸** | 背景方案与模糊类型、日/夜主题跟随、封面缩放基准与大小、封面圆角/阴影/描边、暂停反馈各项 |
| **歌名** | 显隐、行顺序、字号、字体、颜色、加粗、折行规则、阴影、描边 |
| **歌手 / 专辑** | 同上，各页独立设置 |
| **歌曲信息** | 显隐、行顺序、信息模板（`{format}` `{samplerate}` `{bitrate}` `{bits}` `{duration}`）、样式 |
| **排版** | 行间距、文字偏移、水平与垂直对齐 |
| **面板** | 频谱刷新率与锁定、歌词显隐与样式 |
| **系统** | 开机自启、退出时恢复原壁纸 |

---

## ❓ 常见问题

<details>
<summary><b>壁纸不随歌曲更新</b></summary>

查看日志 `%LOCALAPPDATA%\aimp-wallpaper\aimp-wallpaper.log`。AIMP 未运行时程序每 5 秒自动重连；显示器断开（如合盖）已做自动跳过处理。若仍异常，请携带日志提交 Issue。
</details>

<details>
<summary><b>歌词无法获取</b></summary>

歌词按「本地缓存 → 歌曲同目录 `.lrc` → 网易云在线」三级查找。网易云接口为非官方公开接口，可能失效；可将 `.lrc` 文件置于歌曲同目录（与音频同名），歌词窗支持原文/译文对照。
</details>

<details>
<summary><b>歌曲信息行未显示</b></summary>

采样率、比特率、文件大小与时长均取自 AIMP，任何情况都能显示；位深需要读取本地音频文件（有损格式本身没有位深）。缺失的项目直接省略不显示，全部缺失时整行隐藏。
</details>

<details>
<summary><b>频谱面板空白</b></summary>

频谱数据来自系统声音的 WASAPI 环回采集，无声音输出时所有频段自动隐藏，属正常表现。
</details>

---

## 🛠️ 从源码构建

**前置**：[Python](https://www.python.org/) 3.12+、[uv](https://docs.astral.sh/uv/)；打包另需 [Inno Setup](https://jrsoftware.org/isinfo.php) 6+

```bash
uv sync                                   # 安装依赖
uv run python -m aimp_wallpaper           # 运行
uv run python -m aimp_wallpaper restore   # 恢复原壁纸

# 打包 exe
uv run pyinstaller --noconfirm --clean --windowed --name aimp-wallpaper \
  --icon assets/icon.ico --add-data "assets/icon.png;." \
  --collect-all pyaudiowpatch --collect-all pystray run.py

# 生成安装包
iscc installer.iss
```

---

## 📁 项目结构

```
aimp_wallpaper/
├── __main__.py        # 入口：单实例、托盘、面板与歌词窗、渲染线程
├── wallpaper.py       # 海报渲染管线（背景/折行/逐行样式/暂停反馈/音频信息）
├── aimp_api.py        # AIMP Remote API 客户端（消息窗口/共享内存/封面推送）
├── audio_spectrum.py  # WASAPI 环回 FFT 频谱
├── vis_panel.py       # ULW 频谱面板
├── lyrics.py          # 歌词获取（缓存/.lrc/网易云）与歌词悬浮窗
├── desktop.py         # ULW 覆盖窗基础设施
├── settings_gui.py    # 设置窗口（八页）
├── tray.py            # 系统托盘
├── config.py          # 配置默认值与旧配置迁移
└── applog.py          # 日志
```

---

## 🔍 技术实现

- **数据源**：AIMP Remote API（窗口消息 + 共享内存 + `WM_COPYDATA` 封面推送），协议常量按 AIMP v5.40.2727 实测校准
- **渲染**：PIL 逐屏渲染、PNG 输出；背景 1/4 降采样后模糊（约 10 倍提速）；封面与背景按内容哈希缓存
- **覆盖窗**：`UpdateLayeredWindow` 逐像素 alpha 原子呈现，顶层窗口 + 压制 Progman 的 z-order 方案（兼容 Win11 26300）
- **设壁纸**：comtypes 直调 `IDesktopWallpaper`，逐屏 `SetWallpaper`
- **折行**：像素级折行，空格断行吸收带屏幕宽度硬上限，任何一行不超出屏幕

---

## 🙏 致谢

- [AIMP](https://www.aimp.ru/) —— 及其开放的 Remote API
- [163MusicLyrics](https://github.com/jitwxs/163MusicLyrics) —— 歌词接口思路
- [Lively Wallpaper](https://github.com/rocksdanister/lively) / [Rainmeter](https://www.rainmeter.net/) —— 覆盖窗实现思路
- [PyAudioWPatch](https://pypi.org/project/PyAudioWPatch/) · [pystray](https://pypi.org/project/pystray/) · [Pillow](https://python-pillow.org/) · [comtypes](https://github.com/enthought/comtypes)

---

<div align="center">

本项目基于 [MIT License](LICENSE) 开源。

如对您有帮助，欢迎 Star 支持。

</div>
