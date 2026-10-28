# Changelog

## 0.2.0 — 2026-10-28

第一个跨平台版本：Windows / macOS / Linux 共用同一套代码。

### macOS

- Apple Silicon / Intel 支持：P/E 核心、IOKit Apple GPU（无需 sudo）、APFS 卷、热降频与内存压力、电池状态
- 原生启动脚本 `run.sh` / `run.command`，优先 `uv`，可回退到仓库内 `.venv`
- 音乐卡接入 Music / Spotify（AppleScript）：标题、歌手、专辑、播放进度、暂停状态
- Spotify 会尝试拉取专辑封面；没有封面 URL 时自动降级为纯文字
- 首次读取会请求 macOS「自动化」权限，拒绝后音乐卡保持未播放，不影响其他模块

### 仪表盘

- 8 套主题，`T` 循环、`1`–`8` 直选，配置持久化
- 信息栏：时间进度、世界时钟、农历 / 干支 / 节气 / 月相、逐时天气、延迟与 AQI、行情、音乐、待办 / 便签
- 旋转地球 + 定位标记；终端内股票 / 待办编辑器
- 负载彩色条、双行 60s 图、每核热力色；CJK 感知的截断与跑马灯
- 面板随窗口宽高自动切换，支持 120×34 到 240×55

### 工程

- `ruff` + `pytest`，GitHub Actions 三平台矩阵
- 无头冒烟测试（`tools/smoke.py`）与截图生成（`tools/make_preview.py`）
- 平台适配集中在共享模块内，不复制应用目录
