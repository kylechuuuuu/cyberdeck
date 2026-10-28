# cyberdeck

终端里的赛博控制台：左边是时钟 / 月历 / 天气 / 旋转地球，右边是 btop 风格的机器监控，
全屏时再多一列「时间 / 农历 / 逐时 / 网络质量 / 自选（行情·音乐·待办）」。

支持 **macOS（Apple Silicon / Intel）**、Windows 和 Linux。macOS 下会额外读取 P/E 核心、
Apple GPU（IOKit，无需 sudo）、APFS 卷、热降频 / 内存压力和电池状态。

![preview](docs/preview.png)

```
┌ CYBERDECK ──────────────────────────────────────────────────────────────────┐
│ 23:41  │ CPU 每核条形 + 波形 │ MEM │ DISK │ 进程表（整宽） │ TIME 进度/世界时钟 │
│ 月历   │ GPU 显存/频率/温度  │ SYS │ NET  │ ↑↓ 选择 · S 排序 · K 结束 │ LUNAR 农历/月相 │
│ 天气   │                     │     │      │                  │ 逐时/NET/AQI/自选  │
│ 地球   │                     │     │      │                  │ 行情/音乐/待办      │
└ Q 退出  R 天气  SPACE 自转  +/- 转速  ↑↓ 进程  S 排序  K 结束  T 主题  I 信息栏 ┘
```

## macOS 运行

```bash
brew install uv          # 只需一次
git clone https://github.com/kylechuuuuu/cyberdeck.git
cd cyberdeck
uv run cyberdeck
```

也可以直接在 Finder 里双击 `run.command`（会用 Terminal.app），或在喜欢的终端里执行 `./run.sh`。
`run.sh` 优先用 `uv`；找不到时自动回退到仓库内的 `.venv`（如果已经创建过）。

- **终端**：推荐 Ghostty / iTerm2 / WezTerm / kitty（支持真彩色）。Apple 自带的
  Terminal.app 只有 256 色，地球会丢失部分颜色，启动时会有一次提示。
- **字体**：SF Mono / Menlo / JetBrains Mono 都可以；中文由 PingFang / 冬青黑体自动回退。
  如果 iTerm2 里条形图错位，关闭 Profiles → Text 里的 “Treat ambiguous-width characters as double width”。
- **窗口**：建议 ≥ 110 列 × 30 行；≥ 210 列时右侧会出现信息栏。面板会随高度自动切换布局。

固定城市（默认按出口 IP 自动定位）：

```bash
uv run cyberdeck --city Hangzhou
CYBERDECK_CITY=Shanghai uv run cyberdeck
```

## Windows 运行

```powershell
cd C:\Users\kyle\Desktop\cyberdeck
uv run cyberdeck
```

或直接双击 / 运行 `.\run.ps1`。

固定城市：

```powershell
uv run cyberdeck --city Hangzhou
$env:CYBERDECK_CITY = "Shanghai"; uv run cyberdeck
```

要求：Windows Terminal（或任何真彩色终端），建议窗口 ≥ 110 列 × 30 行（更小会显示提示）。
字体用等宽字体（Cascadia Mono / JetBrains Mono / Consolas）。

## Linux

```bash
uv run cyberdeck
```

NVIDIA 显卡走 `nvidia-smi`；配置走 `$XDG_CONFIG_HOME/cyberdeck` 或 `~/.config/cyberdeck`，
天气缓存走 `$XDG_CACHE_HOME/cyberdeck` 或 `~/.cache/cyberdeck`。

## 布局随窗口变化

| 窗口 | 右栏 |
| --- | --- |
| ≥ 210 列 | 硬件两栏 + 进程表，另加最右「信息栏」（可用 `i` 关闭） |
| ≥ 150 列，高度 ≥ 48 行 | 硬件卡片在上，进程表整宽在下 |
| 常规 | 硬件两列（CPU/MEM/DISK/SYS ｜ GPU/NET/PROC） |
| 窄窗口 | 单列，自动保留 CPU/MEM/GPU/进程表 |

## 快捷键

| 键 | 作用 |
| --- | --- |
| `q` / `ctrl+c` | 退出 |
| `r` | 立即刷新天气 |
| `space` | 暂停 / 继续地球自转 |
| `+` / `-` | 加快 / 减慢自转（macOS 上 `+` 即 `shift` + `=`） |
| `t` | 循环切换主题 |
| `1` … `8` | 直接选择主题 |
| `↑` / `↓` | 选择进程 |
| `s` | 进程排序：CPU → 内存 → PID → 名称 |
| `k` 再 `Enter` | 结束选中进程（`Esc` 取消） |
| `i` | 显示 / 隐藏最右信息栏 |
| `e` | 编辑股票代码 / 待办清单 |

主题、城市、信息栏开关都会写进 `config.json`，下次启动自动恢复。

## 终端内编辑（`e`）

![editor](docs/editor.png)

一个弹窗同时改两样东西：

- **股票代码**：逗号分隔，`sh` / `sz` / `hk` / `us` 前缀都可以（`sh600519, sz399001, us.AAPL`）
- **待办**：一行一条，`[x]` 表示已完成，`#` 开头是注释

`Ctrl+S` 保存（写回 `config.json` 和 `todo.txt` 并立即刷新），`Esc` 取消。文件本身也可以直接用编辑器改，面板会按修改时间自动重读。

## 地球定位标注

天气数据里带回城市坐标后，地球表面会出现一个**脉动的红色标记**，旁边标着城市名；转到背面时自动隐藏（`MERIDIAN` 读数会同步显示当前正对的经线）。


## 主题

8 套内置主题，同时作用于面板和地球（海洋/陆地/冰盖/大气）：

| # | 名称 | 风格 |
| --- | --- | --- |
| 1 | 赛博霓虹 | 青 + 紫 + 品红 |
| 2 | BTOP 绿 | btop 同款 |
| 3 | 琥珀 CRT | 单色琥珀 |
| 4 | 矩阵绿 | Matrix |
| 5 | Nord | 冷灰蓝 |
| 6 | Gruvbox | 暖复古 |
| 7 | Tokyo Night | 深蓝紫 |
| 8 | Synthwave | 紫 + 品红 |

## 信息栏（自定义区域）

全屏时右侧多出的这一列由 `config.json` 里的 `info` 段控制，改完重启生效：

```json
{
  "theme": "neon",
  "info": {
    "enabled": true,
    "modules": ["stocks", "media", "todo", "notes"],
    "stocks": ["sh000001", "sz399001", "sh600519", "usNVDA", "usAAPL", "usGOOGL", "usMSFT"],
    "zones": ["UTC", "America/New_York", "Europe/London", "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney"],
    "todo_file": null,
    "notes_file": null
  }
}
```

| 模块 | 内容 | 数据源 |
| --- | --- | --- |
| TIME | 今日/本周/本月/今年进度 + 世界时钟 | 本地 |
| LUNAR | 农历、干支、节气、月相 | lunar_python + 本地月相计算 |
| 逐时 | 未来 8 小时温度/天气 + 温度曲线 | wttr.in 缓存 |
| NET | 延迟/抖动/丢包 + AQI/PM2.5 | TCP 握手 + Open-Meteo |
| stocks | 上证/深证/个股（`sh`/`sz`/`us` 前缀） | 腾讯行情 |
| media | 正在播放：律动条 + 标题 + 歌手 + 进度条 | Windows 媒体会话（winrt）；macOS / Linux 显示「未在播放」 |
| todo | 待办清单 | `todo_file` 或各平台数据目录下的 `todo.txt` |
| notes | 自由便签（任意文本，最多 10 行） | `notes_file` 或各平台数据目录下的 `notes.txt` |

- `modules` 里删掉某一项即可隐藏该模块；想加行情就把代码写进 `stocks`（如 `us.AAPL`、`hk.HSIC`）。
- 待办文件格式：每行一条，`[ ]` 未完成、`[x]` 已完成，`#` 开头是注释。
- 网络类模块失败只显示 `--`，不会卡界面；`media` 在非 Windows 或缺少 winrt 时自动隐藏内容。

## 性能

屏幕越大越吃资源，所以做了几层控制：

- **地球**：目标 10 fps（单帧 > 13 ms 自动降到 7 fps，暂停后 4 fps 只保留星光闪烁）；颜色量化到 4 bit 并把连续同色像素合并，单帧 span 从 ~3400 降到 ~1800，Text 构建 9 ms → 3 ms；一帧总耗时约 10 ms。
- **采样分层**：CPU/内存 1 s，GPU/进程 4 s，ACPI 温度 60 s，行情 60 s，天气 15 min，AQI 10 min，媒体 10 s，延迟 5 s。
- **按需 IO**：待办/笔记文件按 mtime 读取；配置只在改动时写。
- **窄窗口**：右栏回落单列，只保留必要的区块；窗口小于 110×30 直接只显示提示。
- **macOS**：GPU 走一次约 10 ms 的 `ioreg`，CPU 降频 / 内存压力每 8 秒读一次；不需要 sudo，也不跑常驻轮询。

如果还想更省电，把 `globe.py` 里的 `target = 1 / 10` 改成 `1 / 6` 即可。

## 硬件数据来源

| 项目 | macOS | Windows / Linux |
| --- | --- | --- |
| CPU | `sysctl` 型号、P/E 核心拆分、每核占用、线程/FD | psutil：型号、频率、每核占用、线程/句柄 |
| 内存 / Swap | psutil；已用按 `total - available`，并显示 `vm.memory_pressure` 告警 | psutil |
| GPU | `ioreg` 读 IOAccelerator：占用、统一内存、GPU 核心数；无 sudo 不读温度/功耗 | `nvidia-smi`：占用、显存、温度、功耗、频率、编解码 |
| 磁盘 | APFS `Data` 卷合并显示为 `/`，外加 `/Volumes/*` 外置盘；聚合读写速率 | psutil + `Win32_DiskDrive`（型号），每块物理盘读写 |
| 网卡 | `en*` 物理接口 + IPv4；排除 lo0 / AWDL / utun 重复流量 | psutil `net_if_stats` |
| 温度 / 功耗 | GPU 温度/功耗需 sudo，默认不显示；CPU 降频上限来自 `pmset -g therm`（`THR xx%`） | ACPI 热区 + nvidia-smi |
| 电池 | psutil：百分比 + AC / 剩余时间 | psutil |
| 进程 | psutil：CPU / 内存 / 线程 / FD / 启动时间 | psutil：CPU / 内存 / 线程 / 句柄 |

macOS 的 GPU 温度 / 功耗需要 `sudo powermetrics`，因此默认不读取；CPU 降频时
CPU 区会显示琥珀色 `THR xx%`，内存压力高时 MEM 百分比变黄 / 变红并带 `⚠`。

没有装 LibreHardwareMonitor 时 Windows 读不到 CPU 风扇和逐核温度；装了的话命名空间可被探测（后续可接）。
GPU 风扇/功耗上限在部分笔记本上返回 N/A，会自动隐藏。

## 存储位置

配置、待办和便签（`config.json` / `todo.txt` / `notes.txt`）与天气缓存分开存放，均取第一个可写位置：

- **macOS**
  - 配置/待办：`~/Library/Application Support/cyberdeck/`
  - 天气缓存：`~/Library/Caches/cyberdeck/weather.json`
- **Windows**：`%LOCALAPPDATA%\cyberdeck\`，失败时回退 `~/.config/cyberdeck`、`~/.cache/cyberdeck`、`%TEMP%`、`./.cyberdeck`
- **Linux**：`$XDG_CONFIG_HOME/cyberdeck` / `$XDG_CACHE_HOME/cyberdeck`，否则 `~/.config` / `~/.cache`
- 兜底：系统临时目录、`./.cyberdeck`

## 结构

```
run.sh / run.command   macOS 启动脚本
run.ps1 / run.cmd      Windows 启动脚本
src/cyberdeck/
  app.py             Textual 应用、布局、键位、主题切换与持久化
  theme.py           8 套调色板、渐变、条形图 / 波形工具
  globe.py           地球引擎（numpy 投影 + 光照 + 定位标注）+ 控件
  clock.py           大字时钟 + 月历
  weather.py         wttr.in 客户端 + 天气卡片
  system.py          psutil / nvidia-smi / IOKit 采样 + 自适应硬件面板 + 进程表
  extras.py          信息栏：时间进度/农历/逐时/延迟/AQI/行情/音乐/待办
  editor.py          终端内股票 / 待办编辑器
  storage.py         跨平台配置/缓存路径探测
  bigfont.py         5 行像素数字字体
  data/landmask.npz  预烘陆地掩膜
tools/
  build_landmask.py  重新生成陆地掩膜
  make_preview.py    生成 README 截图（Textual 截图 + resvg）
  preview_dash.py    把各面板光栅化成 PNG（开发用）
  smoke.py           无头挂载 + 按键冒烟测试
tests/test_core.py   投影、解析、排版、主题、信息栏、进程表单测
```

## 开发

```bash
uv sync
uv run pytest -q
uv run ruff check src tests tools
uv run python tools/build_landmask.py   # 重新下载海岸线并烘焙掩膜
uv run python tools/smoke.py           # 无头跑一遍，导出 SVG 截图
uv run python tools/make_preview.py    # 重新生成 docs/preview.png
```

`tools/preview_dash.py` 会按平台自动挑选等宽字体 / 中文字体（macOS 用 Menlo + 冬青黑体，
Windows 用 Consolas + 黑体，Linux 用 DejaVu Sans Mono + Noto CJK）。

