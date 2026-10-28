# cyberdeck

终端里的赛博控制台：左边是时钟 / 月历 / 天气 / 旋转地球，右边是 btop 风格的机器监控。

![preview](docs/preview.png)

```
┌ CYBERDECK ───────────────────────────────────────────────┐
│ 23:41     │ CPU  i7-12700H  14C/20T 2.30GHz + 每核心条形 │
│ 10月27日 周二 2026 │ MEM / SWAP                              │
│ 月历 · 高亮今天    │ GPU  3060  占用 / 显存 / 温度 / 功耗     │
│ 天气 · 今天+两天   │ NET + DISK IO + 60s 波形                │
│ 旋转地球 + 星野    │ 磁盘 / TOP 进程 / 运行时长               │
└ Q 退出  R 刷新天气  SPACE 暂停自转  +/- 转速  T 配色 ─────┘
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
字体用等宽字体（Cascadia Mono / JetBrains Mono / Consolas）。

## 快捷键

| 键 | 作用 |
| --- | --- |
| `q` / `ctrl+c` | 退出 |
| `r` | 立即刷新天气 |
| `space` | 暂停 / 继续地球自转 |
| `+` / `-` | 加快 / 减慢自转 |
| `t` | 切换配色（霓虹 / btop 绿 / 琥珀 CRT） |

## 天气

数据来自 [wttr.in](https://wttr.in)，不需要 API key：当前温度、体感、湿度、风向风速、气压、
三日预报、日出日落。每 15 分钟刷新一次，结果缓存到本机；断网时显示上次缓存并标注「缓存」。
缓存依次尝试 `%LOCALAPPDATA%\cyberdeck`、`~/.cache/cyberdeck`、`%TEMP%`、`./.cyberdeck`。

## 地球

- 陆地纹理来自 Natural Earth 110m 海岸线，预烘成 0.5° 等距圆柱掩膜（`data/landmask.npz`）。
- 每帧用 numpy 做正交球面投影 + 23.4° 轴倾 + 固定太阳方向（晨昏线、夜面城市灯光、海面高光、
  大气边缘散射），再打包成半砖块 `▀` 字符，上下像素各用一种真彩色。
- 15 fps，一帧约 1.6 ms（72×26 单元格）。

## 结构

```
src/cyberdeck/
  app.py             Textual 应用、布局、键位、配色切换
  theme.py           调色板、渐变、条形图 / 波形工具
  globe.py           地球引擎（numpy 投影 + 光照）+ 控件
  clock.py           大字时钟 + 月历
  weather.py         wttr.in 客户端 + 天气卡片
  system.py          psutil / nvidia-smi 采样 + 硬件面板
  bigfont.py         5 行像素数字字体
  data/landmask.npz  预烘陆地掩膜
tools/
  build_landmask.py  重新生成陆地掩膜
  preview_dash.py    把各面板光栅化成 PNG（开发用）
  smoke.py           无头挂载 + 按键冒烟测试
tests/test_core.py   投影、解析、排版单测
```

## 开发

```powershell
uv sync
uv run pytest -q
uv run python tools/build_landmask.py   # 重新下载海岸线并烘焙掩膜
uv run python tools/smoke.py           # 无头跑一遍，导出 SVG 截图
```
