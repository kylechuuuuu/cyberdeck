# cyberdeck

[中文](README.md) | **English**

A cyberdeck for your terminal: clock / calendar / weather / spinning Earth on the left,
a btop-style hardware monitor on the right, and — at full width — a third column with
time progress, the lunar calendar, hourly forecast, network quality and a custom zone
(quotes, music, todo).

Runs on **macOS (Apple Silicon / Intel)**, Windows and Linux. On macOS it also reads
P/E cores, the Apple GPU through IOKit (no sudo), APFS volumes, thermal throttling,
memory pressure and battery state. Location defaults to the OS timezone and can be
pinned to exact coordinates from the `e` editor (VPN-safe).

![preview](docs/preview.png)

macOS screenshot: [docs/preview-macos.png](docs/preview-macos.png) (Apple M5 / ioreg GPU / P+E cores)

```
┌ CYBERDECK ──────────────────────────────────────────────────────────────────┐
│ 23:41  │ CPU per-core bars + graph │ MEM │ DISK │ PROC (full width) │ TIME   │
│ 2026   │ GPU VRAM / clocks / temp  │ SYS │ NET  │ ↑↓ select · S sort │ LUNAR  │
│ weather│                           │     │      │ K kill            │ hour/AQI│
│ Earth  │                           │     │      │                   │ quotes │
└ Q quit  R weather  SPACE spin  +/- speed  ↑↓ proc  S sort  K kill  T theme  I info ┘
```

The interface itself is Chinese; the code, docs and commits are English.

## Running on macOS

```bash
brew install uv          # once
git clone https://github.com/kylechuuuuu/cyberdeck.git
cd cyberdeck
uv run cyberdeck
```

You can also double-click `run.command` in Finder (it opens Terminal.app) or run
`./run.sh` in whichever terminal you prefer. `run.sh` uses `uv` when available and
falls back to the repo's `.venv`.

- **Terminal**: Ghostty / iTerm2 / WezTerm / kitty (truecolor). Apple's Terminal.app is
  256 colours only, so the Earth loses some detail — the app warns once at startup.
- **Font**: SF Mono / Menlo / JetBrains Mono all work; Chinese falls back to PingFang.
  If bars look misaligned in iTerm2, turn off Profiles → Text → "Treat ambiguous-width
  characters as double width".
- **Window**: ≥ 110 × 30 cells; the info column appears at ≥ 210 columns, and the
  layout switches by height on its own.

Pick a city (the default comes from the **OS timezone**, so a VPN does not move you to
the exit node's city):

```bash
uv run cyberdeck --city Hangzhou
CYBERDECK_CITY=Shanghai uv run cyberdeck
```

Always-on / low power:

```bash
uv run cyberdeck --fps 5      # the sensible default for a permanent dashboard
uv run cyberdeck --still      # Earth frozen, lowest CPU (space also pauses it)
```

`--fps` can also live in `config.json` as `"fps": 5`.

## Always-on (macOS)

Run it under tmux so closing the terminal or dropping an SSH session does not matter:

```bash
brew install tmux
tmux new -d -s deck 'cd ~/Desktop/cyberdeck && ./run.sh --fps 5'
tmux attach -t deck        # come back any time; leave with ctrl+b then d
```

- `run.sh` passes its arguments straight through to `cyberdeck`.
- Restart on crash:
  `tmux new -d -s deck 'cd ~/Desktop/cyberdeck && while :; do ./run.sh --fps 5; [ $? -eq 0 ] && break; sleep 2; done'`
  (quitting with `q` exits 0 and stops the loop; only a crash restarts it).
- Keep the display awake on AC: `caffeinate -dis ./run.sh --fps 5` (`-d` blocks display
  sleep; use `-i` if you only want to stop idle sleep).
- Start at login: add `run.command` to System Settings → General → Login Items, or create
  the tmux session from a launchd job.
- Remote: `ssh` in and `tmux attach -t deck` — no extra ports.

## Running on Windows

```powershell
cd C:\Users\kyle\Desktop\cyberdeck
uv run cyberdeck
```

Or run `.\run.ps1` (double-click works too).

Pick a city (same timezone-based default):

```powershell
uv run cyberdeck --city Hangzhou
$env:CYBERDECK_CITY = "Shanghai"; uv run cyberdeck
```

Requires Windows Terminal (or any truecolor terminal), ≥ 110 × 30 cells, and a
monospace font (Cascadia Mono / JetBrains Mono / Consolas).

## Linux

```bash
uv run cyberdeck
```

NVIDIA cards go through `nvidia-smi`; config lives in `$XDG_CONFIG_HOME/cyberdeck`
or `~/.config/cyberdeck`, the weather cache in `$XDG_CACHE_HOME/cyberdeck` or
`~/.cache/cyberdeck`.

The music card uses `playerctl` (MPRIS) when installed:

```bash
sudo apt install playerctl        # Debian / Ubuntu
sudo dnf install playerctl        # Fedora
```

Without it the card shows "not playing"; nothing else is affected.

## Layout follows the window

| Window | Right side |
| --- | --- |
| ≥ 210 columns | two hardware columns + process table, plus the info column (`i` hides it) |
| ≥ 150 columns, ≥ 48 rows | hardware cards on top (load bar + two-row 60 s graph, cyan → purple → red by load), full-width process table below |
| Standard | two hardware columns (CPU/MEM/DISK/SYS ｜ GPU/NET/PROC) |
| Narrow | single column with CPU/MEM/GPU/PROC only |

## Keys

| Key | Action |
| --- | --- |
| `q` / `ctrl+c` | quit |
| `r` | refresh weather now |
| `space` | pause / resume the spin (no redraws while paused — cheapest state) |
| `+` / `-` | faster / slower spin (on macOS `+` is `shift` + `=`) |
| `t` | cycle themes |
| `1` … `8` | pick a theme directly |
| `↑` / `↓` | select a process |
| `s` | sort processes: CPU → memory → PID → name |
| `k` then `Enter` | kill the selected process (`Esc` cancels) |
| `i` | show / hide the info column |
| `e` | edit stock symbols, location and the todo list |

Theme, city, location and the info toggle are persisted to `config.json`.

## In-terminal editor (`e`)

![editor](docs/editor.png)

One dialog, three things:

- **Stock symbols**: comma separated, `sh` / `sz` / `hk` / `us` prefixes (`sh600519, sz399001, us.AAPL`)
- **Location**: `lat, lon, city` (`30.2741, 120.1551, Hangzhou`); leave it blank to fall back to the timezone
- **Todo**: one item per line, `[x]` for done, `#` for comments

`Ctrl+S` saves (writes `config.json` and `todo.txt`, and moves the pin and weather city
immediately), `Esc` cancels. The files can be edited directly too — panels re-read them
on mtime.

## Globe location pin

The Earth carries a red **reticle**: white core, breathing ring, expanding radar ping and
four ticks, over a dark cushion so it stays readable on ice, desert and bright ocean. The
label shows the city and its coordinates (`◉ Shanghai 31.3N 121.5E`) and flips to the
other side near a limb.

When the point rotates behind the globe it does not just vanish — a dim `◂ HERE` / `HERE ▸`
parks on the rim, so you always know where it went.

Where the coordinates come from:

1. **Manual**: press `e` and fill the location line, or set `location` in `config.json` —
   exact, applied within 5-10 seconds
2. **OS timezone** (`China Standard Time` → Shanghai) → wttr.in returns that city's
   station coordinates

**Why not IP geolocation**: behind a VPN the exit IP is in Tokyo, so an IP database puts
you in Tokyo and both the weather and the pin are wrong. The OS timezone follows the
machine, not the proxy.

> Older builds may have written `"city": "Tokyo"` into `config.json`; delete that line
> (or set your own city) and restart.

```json
{
  "location": { "lat": 31.2304, "lon": 121.4737, "name": "Shanghai" }
}
```

The globe re-reads this every 5 seconds, the weather city follows, and `location` survives a theme switch.
`name` doubles as the weather city; without it the coordinates are queried directly. Clearing the field returns to the OS timezone (`--city` still wins).

## Keeping it running (Windows)

```powershell
.\run.ps1 -Loop      # restart on crash; q or ctrl+c still exits normally
```

Start at login (maximised):

```powershell
$act = New-ScheduledTaskAction -Execute "pwsh" `
  -Argument "-NoProfile -File `"$HOME\Desktop\cyberdeck\run.ps1`" -Loop"
Register-ScheduledTask -TaskName cyberdeck -Action $act `
  -Trigger (New-ScheduledTaskTrigger -AtLogOn) -RunLevel Limited
```

Notes for a dashboard that stays up:

- Stop the display sleeping: `powercfg /change monitor-timeout-ac 0` (on AC)
- Check for leaks: `uv run python tools/soak.py --seconds 180` — flat is healthy; only a
  rising last third means something accumulates
- Network failures stay local: quotes, weather and AQI each keep their last data
- The Earth runs at 8 fps (roughly 20-25% of one core on an M5, see the table below); `--fps 1..30` tunes it, `--still`
  freezes it (~4%), and `space` pauses with no redraws at all

## Themes

Eight palettes, applied to panels and the Earth (ocean / land / ice / atmosphere):

| # | Name | Look |
| --- | --- | --- |
| 1 | Cyber neon | cyan + purple + magenta |
| 2 | btop green | same as btop |
| 3 | Amber CRT | monochrome amber |
| 4 | Matrix | green on black |
| 5 | Nord | cool grey-blue |
| 6 | Gruvbox | warm retro |
| 7 | Tokyo Night | deep blue-purple |
| 8 | Synthwave | purple + magenta |

## Info column

At full width the extra column is driven by the `info` section of `config.json`
(restart after editing):

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

| Module | Contents | Source |
| --- | --- | --- |
| TIME | day / week / month / year progress + world clocks | local |
| LUNAR | lunar date, sexagenary cycle, solar terms, moon phase | lunar_python + local astronomy |
| Hourly | next 8 hours, temperature and weather, with a curve | wttr.in cache |
| NET | latency / jitter / loss + AQI / PM2.5 | TCP handshake + Open-Meteo |
| stocks | SSE / SZSE indices and symbols (`sh` / `sz` / `us`) | Tencent quotes |
| media | album art, equaliser, title/artist/album, gradient progress (extrapolated, 1 s) | Windows media session (winrt); macOS drives Music / Spotify; Linux uses `playerctl` |
| todo | checklist | `todo_file` or `todo.txt` in the platform data dir |
| notes | free-form notes (up to 10 lines) | `notes_file` or `notes.txt` |

- Drop an entry from `modules` to hide it; add symbols to `stocks` (e.g. `us.AAPL`, `hk.HSIC`).
- Todo format: one item per line, `[ ]` open, `[x]` done, `#` for comments.
- Network modules degrade to `--` instead of blocking the UI.
- The first time macOS reads Music / Spotify the system asks for Automation permission;
  declining leaves the card empty and nothing else breaks. Spotify also yields cover art;
  Music.app only gives text.

## Performance

Bigger screens cost more, so there are several layers of control:

- **Earth**: 8 fps by default (`--fps 1..30`), no redraws while paused; colours are
  quantised to 4 bit and runs of identical pixels are merged, cutting a frame from
  ~3400 to ~1800 spans and Text building from 9 ms to 3 ms.
- **Redraw on demand**: clock 1 s; the info column only redraws when the minute changes or
  todo/notes/quotes/media change; the progress bar ticks at 1 s only while playing;
  weather cache and todo files are read by mtime.
- **Layered sampling**: CPU/memory 1 s, GPU/processes 4 s, ACPI temperature 60 s, quotes
  60 s, weather 15 min, AQI 10 min, media 10 s, latency 5 s.
- **Narrow windows**: the right side collapses to one column; below 110×30 only a hint is drawn.
- **macOS**: the GPU costs one ~10 ms `ioreg` read; throttle and memory pressure are read
  every 8 s. No sudo, no resident polling.

Measured on an Apple M5, 160×44 (percent of one core, app only):

| Mode | CPU | Notes |
| --- | --- | --- |
| default 8 fps | ~23% | smooth |
| `--fps 5` | ~19% | recommended for a permanent dashboard |
| `--fps 4` | ~16% | lighter, slight stepping |
| `--still` | ~4% | frozen Earth, pure dashboard |

## Where the hardware numbers come from

| Item | macOS | Windows / Linux |
| --- | --- | --- |
| CPU | `sysctl` model, P/E split, per-core load, threads/FDs | psutil: model, frequency, per-core load, threads/handles |
| Memory / swap | psutil; used = `total - available`, plus `vm.memory_pressure` warnings | psutil |
| GPU | `ioreg` IOAccelerator: utilisation, unified memory, core count; no temperature/power without sudo | `nvidia-smi`: utilisation, VRAM, temperature, power, clocks, encoders |
| Disk | APFS `Data` volume merged into `/`, plus `/Volumes/*`; aggregate throughput | psutil + `Win32_DiskDrive` models, per-disk throughput |
| NIC | `en*` physical interfaces + IPv4; lo0 / AWDL / utun filtered out | psutil `net_if_stats` |
| Temperature / power | GPU values need sudo, hidden by default; CPU throttle from `pmset -g therm` (`THR xx%`) | ACPI thermal zones + nvidia-smi |
| Battery | psutil: percentage, AC state, time left | psutil |
| Processes | psutil: CPU / memory / threads / FDs / start time | psutil: CPU / memory / threads / handles |

macOS GPU temperature and power need `sudo powermetrics`, so they are not read by default.
When the CPU is throttled the CPU block shows an amber `THR xx%`; high memory pressure turns
the MEM percentage amber or red and adds `⚠`.

Without LibreHardwareMonitor, Windows exposes no CPU fan or per-core temperatures; the
namespace is probed and can be wired up later. GPU fan/power limits come back as N/A on
some laptops and are hidden.

## Where state lives

Config, todo and notes (`config.json` / `todo.txt` / `notes.txt`) are kept apart from the
weather cache; each takes the first writable location:

- **macOS**
  - config/todo: `~/Library/Application Support/cyberdeck/`
  - weather cache: `~/Library/Caches/cyberdeck/weather.json`
- **Windows**: `%LOCALAPPDATA%\cyberdeck\`, falling back to `~/.config/cyberdeck`,
  `~/.cache/cyberdeck`, `%TEMP%`, `./.cyberdeck`
- **Linux**: `$XDG_CONFIG_HOME/cyberdeck` / `$XDG_CACHE_HOME/cyberdeck`, else
  `~/.config` / `~/.cache`
- Last resort: the system temp dir, `./.cyberdeck`

## Repository layout

```
run.sh / run.command   macOS launchers
run.ps1 / run.cmd      Windows launchers
src/cyberdeck/
  app.py             Textual app: layout, bindings, themes, persistence
  theme.py           8 palettes, ramps, bar / graph helpers
  globe.py           Earth engine (numpy projection + lighting + pin) and widget
  clock.py           pixel clock + calendar
  weather.py         wttr.in client + weather card
  system.py          psutil / nvidia-smi / IOKit sampling, hardware panels, process table
  extras.py          info column: time, lunar, hourly, latency, AQI, quotes, media, todo
  editor.py          in-terminal editor for symbols / location / todo
  geo.py             city from the OS timezone, manual location parsing
  storage.py         cross-platform config and cache paths
  bigfont.py         5-row pixel digit font
  data/landmask.npz  pre-baked land mask
tools/
  build_landmask.py  rebuild the land mask
  make_preview.py    README screenshot (Textual export + resvg)
  make_editor_preview.py   editor screenshot
  preview_dash.py    rasterise panels to PNG (development aid)
  soak.py            RSS soak test for long runs
  smoke.py           headless mount + keypress smoke test
tests/test_core.py   projection, parsing, layout, themes, info column, process table
```

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check src tests tools
uv run python tools/build_landmask.py   # re-download coastlines and bake the mask
uv run python tools/smoke.py           # headless run, exports SVG screenshots
uv run python tools/make_preview.py    # Windows → docs/preview.png; macOS → docs/preview-macos.png
```

`tools/preview_dash.py` picks the platform monospace and CJK fonts (Menlo + PingFang on
macOS, Consolas + Microsoft YaHei on Windows, DejaVu Sans Mono + Noto CJK on Linux).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
