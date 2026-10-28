# cyberdeck

终端里的赛博控制台：左边是时钟 / 月历 / 天气 / 旋转地球，右边是 btop 风格的机器监控。

![preview](docs/preview.png)

```
┌ CYBERDECK ───────────────────────────────────────────────────────────┐
│ 23:41    │ CPU  每核条形 + 历史波形 │ GPU  占用/显存/频率/温度          │
│ 月历     │ MEM / SWAP              │ NET  网卡速率 + IPv4 + 波形       │
│ 天气     │ DISK 分区 + 每盘 IO     │ PROC 可选中进程表（↑↓ / S / K）    │
│ 地球     │ SYS  温度/线程/句柄/CTX │                                  │
└ Q 退出  R 天气  SPACE 自转  +/- 转速  ↑↓ 进程  S 排序  K 结束  T 主题 ┘
```

## 运行

```powershell
cd C:\Users\kyle\Desktop\cyberdeck
uv run cyberdeck
```

或直接双击 / 运行 `.\run.ps1`。

固定城市（默认按出口 IP 自动定位）：

```powershell
uv run cyberdeck --city Hangzhou
$env:CYBERDECK_CITY = "Shanghai"; uv run cyberdeck
```

要求：Windows Terminal（或任何真彩色终端），建议窗口 ≥ 110 列 × 30 行（更小会显示提示）。
窗口 ≥ 150 列时右栏自动切成两列卡片，窄窗口自动回落单列并隐藏次要区块。
字体用等宽字体（Cascadia Mono / JetBrains Mono / Consolas）。

## 快捷键

| 键 | 作用 |
| --- | --- |
| `q` / `ctrl+c` | 退出 |
| `r` | 立即刷新天气 |
| `space` | 暂停 / 继续地球自转 |
| `+` / `-` | 加快 / 减慢自转 |
| `t` | 循环切换主题 |
| `1` … `8` | 直接选择主题 |
| `↑` / `↓` | 选择进程 |
| `s` | 进程排序：CPU → 内存 → PID → 名称 |
| `k` 再 `Enter` | 结束选中进程（`Esc` 取消） |

主题和城市会记到 `config.json`，下次启动自动恢复。

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

## 天气

数据来自 [wttr.in](https://wttr.in)，不需要 API key：当前温度、体感、湿度、风向风速、气压、
三日预报、日出日落。每 15 分钟刷新一次，结果缓存到本机；断网时显示上次缓存并标注「缓存」。

## 硬件数据来源

| 项目 | 来源 |
| --- | --- |
| CPU 总体/每核、频率、线程/句柄、上下文切换 | psutil |
| 内存 / Swap（页面文件） | psutil |
| GPU 占用、显存、温度、功耗、频率、编解码 | `nvidia-smi` |
| 磁盘分区用量、每块物理盘读写速率 | psutil + `Win32_DiskDrive`（型号） |
| 网卡速率 / IPv4 | psutil `net_if_stats` |
| ACPI 热区温度 | `MSAcpi_ThermalZoneTemperature` |
| 电池 | psutil（剩余时间可用时显示） |

没有装 LibreHardwareMonitor 时读不到 CPU 风扇和逐核温度；装了的话命名空间可被探测（后续可接）。
GPU 风扇/功耗上限在部分笔记本上返回 N/A，会自动隐藏。

## 存储位置

配置与天气缓存依次尝试：`%LOCALAPPDATA%\cyberdeck`、`~/.config/cyberdeck`、`~/.cache/cyberdeck`、
`%TEMP%`、`./.cyberdeck`，取第一个可写目录。

## 结构

```
src/cyberdeck/
  app.py             Textual 应用、布局、键位、主题切换与持久化
  theme.py           8 套调色板、渐变、条形图 / 波形工具
  globe.py           地球引擎（numpy 投影 + 光照）+ 控件
  clock.py           大字时钟 + 月历
  weather.py         wttr.in 客户端 + 天气卡片
  system.py          psutil / nvidia-smi 采样 + 双列硬件面板 + 进程表
  storage.py         配置/缓存路径探测
  bigfont.py         5 行像素数字字体
  data/landmask.npz  预烘陆地掩膜
tools/
  build_landmask.py  重新生成陆地掩膜
  preview_dash.py    把各面板光栅化成 PNG（开发用）
  smoke.py           无头挂载 + 按键冒烟测试
tests/test_core.py   投影、解析、排版、主题、进程表单测
```

## 开发

```powershell
uv sync
uv run pytest -q
uv run ruff check src tests tools
uv run python tools/build_landmask.py   # 重新下载海岸线并烘焙掩膜
uv run python tools/smoke.py           # 无头跑一遍，导出 SVG 截图
```
