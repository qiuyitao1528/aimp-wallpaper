<div align="center">

# AIMP Wallpaper

**让桌面壁纸跟着 AIMP 里正在播放的歌一起变**

专辑封面海报式动态壁纸 · AIMP 经典频谱面板 · 桌面歌词 · 零插件依赖

[![Release](https://img.shields.io/github/v/release/qiuyitao1528/aimp-wallpaper?style=flat-square&color=4C8BF5)](https://github.com/qiuyitao1528/aimp-wallpaper/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6?style=flat-square&logo=windows)](https://github.com/qiuyitao1528/aimp-wallpaper)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/qiuyitao1528/aimp-wallpaper?style=flat-square&color=3DA639)](LICENSE)
[![AIMP](https://img.shields.io/badge/AIMP-v5.40%20tested-FF6B35?style=flat-square)](https://www.aimp.ru/)

[下载](#-安装) · [快速开始](#-快速开始) · [配置](#-配置) · [常见问题](#-常见问题) · [从源码构建](#-从源码构建) · [技术实现](#-技术实现)

</div>

---

<div align="center">
<img src="docs/screenshot.png" width="880" alt="AIMP Wallpaper 效果预览">
</div>

---

## ✨ 功能

| | 功能 | 说明 |
|---|---|---|
| 🖼️ | **海报式动态壁纸** | 切歌即换：封面 1:1 清晰居左，右侧歌名/歌手/专辑/歌曲信息四行文字；封面绝不放大、绝不裁剪，超屏才等比缩小 |
| 🌄 | **四种背景方案** | 高斯模糊 / 模糊+暗角 / 原图铺满 / 主色渐变；模糊支持四种高斯系变体（高斯 / 柔焦 / 雾面 / 辉光） |
| 🌙 | **日/夜主题跟随** | 跟随 Windows 深浅色模式，夜间自动叠加黑色遮罩（浓度可调），实时切换无需重启 |
| 🎨 | **逐行排版精调** | 歌名/歌手/专辑/歌曲信息四行各自一页独立设置：字号、字体（枚举系统全部字体）、颜色、加粗、阴影、描边（宽度+颜色）；每行可单独隐藏 |
| 📐 | **智能折行** | 换行模式无省略号、整段展示；空格断行（断点附近遇空格优先断在空格后）、括号断行（括号组保持完整），任何一行绝不超出屏幕 |
| ℹ️ | **歌曲信息行** | `FLAC 48 kHz 1796 kbps 24 bit`——格式/采样率/位深从音频文件头解析，比特率按文件大小与时长计算，模板自由定制 |
| 🎤 | **桌面歌词** | 当前行+下一行悬浮窗，可拖动/锁定，跟随频谱面板；歌词三级来源：本地缓存 → 歌曲同目录 `.lrc` → 网易云在线；样式与壁纸文字同源可调 |
| ⏸️ | **暂停反馈** | AIMP 暂停时壁纸自动压暗或显示「已暂停」角标，恢复播放即还原 |
| 📊 | **经典频谱面板** | 白条+点状峰值帽，与 AIMP 官方可视化同款（线性频率轴，WASAPI 环回自算 FFT）；可拖动、可锁定、10~120fps |
| 🖥️ | **多显示器** | 逐屏按物理分辨率渲染；断开的显示器自动跳过，不影响其余屏幕 |
| ⚡ | **低占用** | 覆盖窗走 `UpdateLayeredWindow` 逐像素 alpha 原子呈现（Rainmeter / Lively 同思路），频谱约 6~8% CPU |
| 🔔 | **系统托盘** | 设置、频谱面板、歌词、恢复原壁纸、退出，一应俱全 |
| 💾 | **不弄脏桌面** | 首次运行自动记录原壁纸，退出（可关）或卸载时自动恢复 |

---

## 📦 安装

**系统要求**：Windows 10 / 11（64 位）+ [AIMP](https://www.aimp.ru/) v5.40（利用其自带 Remote API，**无需安装任何插件**）

前往 [**Releases**](https://github.com/qiuyitao1528/aimp-wallpaper/releases/latest) 下载，二选一：

<table>
<tr>
<td width="50%" valign="top">

### 🔧 安装版
`aimp-wallpaper-vX.Y.Z-setup.exe`

- 免管理员，安装到当前用户目录
- 自带开始菜单快捷方式
- 可选开机自启
- 支持在「添加或删除程序」中卸载，卸载时自动恢复原壁纸

</td>
<td width="50%" valign="top">

### 🟢 绿色版
`aimp-wallpaper-vX.Y.Z-win64.zip`

- 解压即用，不写注册表
- 配置生成在 exe 旁，随目录走
- 适合 U 盘 / 便携场景

</td>
</tr>
</table>

---

## 🚀 快速开始

1. 启动 **AIMP Wallpaper**（首次运行自动记录你当前的原壁纸，用于退出时恢复）
2. 打开 AIMP 播放任意歌曲 —— 壁纸立刻变成这张歌的海报
3. 右下角出现频谱面板，托盘区出现图标

**托盘右键菜单**

> 设置… · 显示/隐藏频谱面板 · 显示/隐藏歌词 · 恢复原壁纸 · 退出

**频谱面板右键**：设置… · 跟随壁纸位置 · 锁定（禁拖动）· 隐藏面板 · 退出
**歌词窗右键**：锁定（禁拖动）/ 隐藏歌词 / 设置…

> 退出程序时默认恢复原壁纸（可在 设置 → 系统 中关闭）；也可随时手动恢复：`aimp-wallpaper.exe restore`

---

## ⚙️ 配置

设置窗口分八页，**全部即改即生效**（保存后壁纸立刻重渲染，无需重启程序）：

| 页签 | 内容 |
|---|---|
| **壁纸** | 背景方案（模糊 / 模糊+暗角 / 原图铺满 / 主色渐变）、模糊类型（高斯 / 柔焦 / 雾面 / 辉光）与强度、日/夜主题跟随及夜间遮罩浓度、封面大小倍率与 X/Y 偏移、封面圆角（自动/4~48px）、封面阴影浓度与偏移、封面描边、暂停显示（关 / 压暗 / 角标 / 压暗+角标）及浓度 |
| **歌名** | 显隐、字号、字体、颜色、加粗、过长处理、阴影、描边、空格断行、括号断行 |
| **歌手** | 同上，独立设置 |
| **专辑** | 同上，独立设置 |
| **歌曲信息** | 显隐、信息模板（`{format}` `{samplerate}` `{bitrate}` `{bits}` `{duration}`）、字号/字体/颜色/阴影/描边（默认从专辑行样式播种） |
| **排版** | 标题-副行间距、标题/副行行间距、文字 X/Y 偏移、水平与垂直对齐 |
| **面板** | 频谱刷新率（15~120fps）、面板锁定、歌词显隐与歌词样式（字体/字号/颜色/描边/阴影） |
| **系统** | 开机自启、退出时恢复原壁纸 |

> 所有像素值可直接键入（支持负数）。频谱面板与歌词窗的自动位置跟随文字块底部，调整排版时会一起挪动。

---

## ❓ 常见问题

<details>
<summary><b>壁纸不跟着歌变？</b></summary>

先看日志：`%LOCALAPPDATA%\aimp-wallpaper\aimp-wallpaper.log`

最常见的两个原因：
- **AIMP 没在运行**：程序会每 5 秒重连，AIMP 启动后自动恢复
- **显示器合盖/断开**：已做自动跳过处理；若仍遇到，请带日志提 Issue
</details>

<details>
<summary><b>歌词抓不到？</b></summary>

歌词按「本地缓存 → 歌曲同目录同名 `.lrc` → 网易云在线」三级查找。网易云接口为非官方公开接口，可能失效——此时可手动把 `.lrc` 放到歌曲同目录（同名），或稍后再试。歌词窗抓取结果会自动缓存，命中后不再联网。
</details>

<details>
<summary><b>歌曲信息行显示不全？</b></summary>

采样率/位深需要能读到音频文件本体：网络播放（URL）或文件被移动后无法解析，对应项显示 `—`；若四项全部未知，整行自动隐藏。模板可在 设置 → 歌曲信息 中修改。
</details>

<details>
<summary><b>频谱面板不动 / 是空的？</b></summary>

面板数据来自系统声音的 WASAPI 环回采集。没有任何声音输出时所有条会整列隐藏（正常表现）；持续空白请检查系统输出设备。
</details>

<details>
<summary><b>在线电台没有封面？</b></summary>

在线流通常不带封面图，此时显示深色占位框（正常行为）。
</details>

<details>
<summary><b>开机自启在哪里开关？</b></summary>

设置 → 系统 → 开机自启动。它与安装包中勾选的「开机自动启动」是同一个启动项；升级安装不会改动你在这里的开关。
</details>

---

## 🛠️ 从源码构建

**前置**：[Python](https://www.python.org/) 3.12+、[uv](https://docs.astral.sh/uv/)、打包发布另需 [Inno Setup](https://jrsoftware.org/isinfo.php) 6+

```bash
# 安装依赖
uv sync

# 运行
uv run python -m aimp_wallpaper          # 启动
uv run python -m aimp_wallpaper restore  # 恢复原壁纸

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
├── wallpaper.py       # 海报渲染管线（背景方案/折行/逐行样式/暂停反馈/音频信息）
├── aimp_api.py        # AIMP Remote API 客户端（消息窗口/共享内存/封面推送）
├── audio_spectrum.py  # WASAPI 环回 FFT 频谱
├── vis_panel.py       # ULW 频谱面板
├── lyrics.py          # 歌词获取（缓存/.lrc/网易云）与歌词悬浮窗
├── desktop.py         # ULW 覆盖窗基础设施（z-order 席位管理）
├── settings_gui.py    # 设置窗口（八页）
├── tray.py            # 系统托盘
├── config.py          # 配置默认值与旧配置迁移
└── applog.py          # 日志（文件轮转 + 异常兜底落盘）
```

---

## 🔍 技术实现

<details>
<summary><b>展开技术细节</b></summary>

- **数据源**：AIMP 自带 Remote API（`AIMP2_RemoteInfo` 窗口消息 + 共享内存 + `WM_COPYDATA` 封面推送），零插件依赖。协议常量按 AIMP v5.40.2727 实测校准
- **封面**：`GET_ALBUMART(29)` → AIMP 回推 `WM_COPYDATA`（`dwData=0x41495043`，图片字节流）。切歌瞬间 AIMP 常未解析好封面，故带重试窗口；同专辑连播走快速路径
- **元数据**：共享内存 2048 字节，`0x00`=字符串区偏移(0x58)，`0x28` 起依次 Album/Artist/Date/FileName/Genre/Title 字符长度（WCHAR 数），`0x58` 起紧凑 UTF-16
- **频谱**：AIMP 官方可视化是线性频率轴直出 FFT bin（见其 `apiVisuals.h`），本项目对齐该实现；采集走 WASAPI 环回（pyaudiowpatch），帧间线性插值
- **渲染**：PIL 逐屏渲染、PNG 输出；模糊背景 1/4 降采样后模糊再放大（约 10 倍提速）；封面与背景按内容哈希缓存，同专辑连播零重复计算
- **折行**：按像素宽度折行，吸收类断行（空格/括号）带「屏幕右缘预算」硬上限——任何一行绝不超出屏幕
- **覆盖窗口**：Win11 26300 上 `SetParent` 进 Progman/WorkerW 的窗口不被 DWM 合成，故采用顶层窗口 + `UpdateLayeredWindow` 逐像素 alpha + `SetWindowPos` 将 Progman 压到窗口下方（Rainmeter / Lively 同思路）
- **设壁纸**：comtypes 手写 `IDesktopWallpaper`（IID `B92B56A9-8B55-4E14-9A89-0199BBB6F93B`，网传 IID 有误），逐屏 `SetWallpaper` + `DWPOS_FILL`

</details>

---

## 🤝 反馈与贡献

遇到问题请先查阅 [常见问题](#-常见问题) 与 [日志](#-常见问题)（`%LOCALAPPDATA%\aimp-wallpaper\aimp-wallpaper.log`），仍无法解决欢迎[提 Issue](https://github.com/qiuyitao1528/aimp-wallpaper/issues)，附上日志会更快定位。PR 同样欢迎。

---

## 🙏 致谢

- [AIMP](https://www.aimp.ru/) —— 优秀的本地音乐播放器，及其开放的 Remote API
- [163MusicLyrics](https://github.com/jitwxs/163MusicLyrics) —— 歌词接口思路参考
- [Lively Wallpaper](https://github.com/rocksdanister/lively) / [Rainmeter](https://www.rainmeter.net/) —— 覆盖窗实现思路
- [PyAudioWPatch](https://pypi.org/project/PyAudioWPatch/) · [pystray](https://pypi.org/project/pystray/) · [Pillow](https://python-pillow.org/) · [comtypes](https://github.com/enthought/comtypes)

---

<div align="center">

**License** · [MIT](LICENSE)

如果它让你的桌面好看了一点，欢迎点个 ⭐

</div>
