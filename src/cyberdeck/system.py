"""Hardware monitor: psutil + nvidia-smi sampling, two-column panel, process table."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import psutil
from rich.cells import cell_len
from rich.text import Text
from textual import work
from textual.widget import Widget

from . import theme

IS_WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if IS_WIN else 0
POWERSHELL = shutil.which("powershell") or "powershell"


@dataclass
class Gpu:
    name: str
    util: float
    mem_used: int  # MiB
    mem_total: int
    temp: float
    power: float
    power_limit: float | None = None
    fan: float | None = None
    clock_gfx: float = 0.0
    clock_mem: float = 0.0
    enc: float = 0.0
    dec: float = 0.0


@dataclass
class Proc:
    name: str
    pid: int
    cpu: float
    rss: int
    threads: int = 0
    handles: int = 0
    created: float = 0.0


@dataclass
class Disk:
    mount: str
    used: int
    total: int


@dataclass
class DiskIO:
    label: str
    read: float
    write: float


@dataclass
class Nic:
    name: str
    speed: float
    ipv4: str
    up: bool


@dataclass
class State:
    cpu: float = 0.0
    per_core: list[float] = field(default_factory=list)
    freq: float = 0.0
    mem_pct: float = 0.0
    mem_used: int = 0
    mem_total: int = 0
    swap_used: int = 0
    swap_total: int = 0
    down: float = 0.0
    up: float = 0.0
    disk_read: float = 0.0
    disk_write: float = 0.0
    disk_ios: list[DiskIO] = field(default_factory=list)
    gpu: Gpu | None = None
    disks: list[Disk] = field(default_factory=list)
    nics: list[Nic] = field(default_factory=list)
    procs: list[Proc] = field(default_factory=list)
    acpi_temp: float | None = None
    ctx_switches: float = 0.0
    threads_total: int = 0
    handles_total: int = 0
    boot_time: float = 0.0
    battery: tuple[float, bool, float] | None = None
    uptime: float = 0.0


def cpu_model() -> str:
    if IS_WIN:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            ) as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "CPU"


def short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def _num(value: str) -> float | None:
    value = value.strip()
    if not value or value.startswith("[") or value.upper() in ("N/A", "NAN"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _gpu_sample() -> Gpu | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    fields = (
        "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,"
        "power.limit,fan.speed,clocks.current.graphics,clocks.current.memory,"
        "utilization.encoder,utilization.decoder"
    )
    try:
        out = subprocess.run(
            [exe, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, creationflags=NO_WINDOW, check=False,
        ).stdout.strip().splitlines()
        if not out:
            return None
        parts = [s.strip() for s in out[0].split(",")]
        return Gpu(
            name=parts[0].replace("NVIDIA ", "").replace(" Laptop GPU", ""),
            util=_num(parts[1]) or 0.0,
            mem_used=int(_num(parts[2]) or 0),
            mem_total=int(_num(parts[3]) or 0),
            temp=_num(parts[4]) or 0.0,
            power=_num(parts[5]) or 0.0,
            power_limit=_num(parts[6]),
            fan=_num(parts[7]),
            clock_gfx=_num(parts[8]) or 0.0,
            clock_mem=_num(parts[9]) or 0.0,
            enc=_num(parts[10]) or 0.0,
            dec=_num(parts[11]) or 0.0,
        )
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def _acpi_temperature() -> float | None:
    """ACPI thermal zone (often the only readable sensor on Windows)."""
    if not IS_WIN:
        return None
    cmd = (
        "(Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature)."
        "CurrentTemperature | ForEach-Object { $_/10-273.15 } | "
        "Measure-Object -Maximum | Select-Object -ExpandProperty Maximum"
    )
    try:
        out = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=6, creationflags=NO_WINDOW, check=False,
        ).stdout.strip().splitlines()
        value = float(out[-1].replace(",", ".")) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if value is None or not 20.0 <= value <= 110.0:
        return None
    return value


def _disk_models() -> dict[int, str]:
    if not IS_WIN:
        return {}
    cmd = 'Get-CimInstance Win32_DiskDrive | ForEach-Object { "$($_.Index)|$($_.Model)" }'
    try:
        out = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    models: dict[int, str] = {}
    for line in out.splitlines():
        if "|" in line:
            idx, _, model = line.partition("|")
            try:
                models[int(idx)] = model.strip()
            except ValueError:
                continue
    return models


class Sampler:
    def __init__(self) -> None:
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        self.ncpu = psutil.cpu_count(logical=True) or 1
        self.cores = psutil.cpu_count(logical=False) or 1
        self.cpu_name = cpu_model()
        self.state = State()
        self.cpu_hist: deque[float] = deque(maxlen=72)
        self.net_hist: deque[float] = deque(maxlen=72)
        self.gpu_hist: deque[float] = deque(maxlen=72)
        self._prev_net = psutil.net_io_counters()
        self._prev_disk = psutil.disk_io_counters()
        self._prev_disk_each = psutil.disk_io_counters(perdisk=True) or {}
        self._prev_t = time.monotonic()
        self._prev_cpu: dict[int, tuple[float, float]] = {}
        self._prev_ctx = psutil.cpu_stats().ctx_switches
        self._slow_t = 0.0
        self._sensor_t = 0.0
        self._disk_models: dict[int, str] | None = None
        self.loaded = False

    # -- fast (every ~0.7 s) ------------------------------------------------
    def fast(self) -> State:
        s = self.state
        s.cpu = psutil.cpu_percent(None)
        s.per_core = psutil.cpu_percent(None, percpu=True)
        self.cpu_hist.append(s.cpu)
        freq = psutil.cpu_freq()
        s.freq = (freq.current / 1000) if freq else 0.0

        vm = psutil.virtual_memory()
        s.mem_pct, s.mem_used, s.mem_total = vm.percent, vm.used, vm.total
        sw = psutil.swap_memory()
        s.swap_used, s.swap_total = sw.used, sw.total

        now = time.monotonic()
        dt = max(1e-3, now - self._prev_t)
        net = psutil.net_io_counters()
        s.down = max(0.0, (net.bytes_recv - self._prev_net.bytes_recv) / dt)
        s.up = max(0.0, (net.bytes_sent - self._prev_net.bytes_sent) / dt)
        self._prev_net, self._prev_t = net, now
        self.net_hist.append(s.down + s.up)

        io = psutil.disk_io_counters()
        if io and self._prev_disk:
            s.disk_read = max(0.0, (io.read_bytes - self._prev_disk.read_bytes) / dt)
            s.disk_write = max(0.0, (io.write_bytes - self._prev_disk.write_bytes) / dt)
        self._prev_disk = io or self._prev_disk

        each = psutil.disk_io_counters(perdisk=True) or {}
        ios: list[DiskIO] = []
        for name, cur in sorted(each.items()):
            if not name.startswith("PhysicalDrive"):
                continue
            prev = self._prev_disk_each.get(name)
            if prev is None:
                continue
            idx = int(name.replace("PhysicalDrive", "") or 0)
            model = (self._disk_models or {}).get(idx, "")
            label = f"D{idx}"
            if model:
                model = model.replace("Micron_", "").replace("_", " ").strip()
                label += " " + short(model.split(" ")[0], 10)
            ios.append(DiskIO(
                label,
                max(0.0, (cur.read_bytes - prev.read_bytes) / dt),
                max(0.0, (cur.write_bytes - prev.write_bytes) / dt),
            ))
        if ios:
            s.disk_ios = ios
        self._prev_disk_each = each

        ctx = psutil.cpu_stats().ctx_switches
        s.ctx_switches = max(0.0, (ctx - self._prev_ctx) / dt)
        self._prev_ctx = ctx

        s.uptime = time.time() - psutil.boot_time()
        s.boot_time = psutil.boot_time()
        bat = psutil.sensors_battery()
        if bat:
            left = bat.secsleft if 0 < bat.secsleft < 86400 else -1
            s.battery = (bat.percent, bat.power_plugged, left)
        return s

    # -- slow (every ~2.5 s) ------------------------------------------------
    def slow(self) -> State:
        s = self.state
        if time.monotonic() - self._slow_t < 2.0:
            return s
        self._slow_t = time.monotonic()

        s.gpu = _gpu_sample()
        self.gpu_hist.append(s.gpu.util if s.gpu else 0.0)

        if self._disk_models is None:
            self._disk_models = _disk_models()

        if time.monotonic() - self._sensor_t > 60:
            self._sensor_t = time.monotonic()
            s.acpi_temp = _acpi_temperature()

        s.disks = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            s.disks.append(Disk(part.device.rstrip("\\") or part.mountpoint, usage.used, usage.total))

        s.nics = self._nics()
        s.procs, s.threads_total, s.handles_total = self._procs()
        self.loaded = True
        return s

    def _nics(self) -> list[Nic]:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        out: list[Nic] = []
        for name, st in stats.items():
            if not st.isup or st.speed <= 0 or "loopback" in name.lower() or "bluetooth" in name.lower():
                continue
            ipv4 = ""
            for addr in addrs.get(name, []):
                if addr.family.name == "AF_INET":
                    ipv4 = addr.address
                    break
            out.append(Nic(name=name, speed=float(st.speed), ipv4=ipv4, up=st.isup))
        out.sort(key=lambda n: n.speed, reverse=True)
        return out[:3]

    def _procs(self, limit: int = 48) -> tuple[list[Proc], int, int]:
        now = time.monotonic()
        out: list[Proc] = []
        seen: dict[int, tuple[float, float]] = {}
        threads_total = handles_total = 0
        for p in psutil.process_iter(
            ["pid", "name", "cpu_times", "memory_info", "num_threads", "num_handles", "create_time"]
        ):
            try:
                info = p.info
                pid = int(info["pid"])
                if pid <= 4:
                    continue
                ct = info["cpu_times"]
                total = ct.user + ct.system
                prev = self._prev_cpu.get(pid)
                seen[pid] = (total, now)
                pct = (total - prev[0]) / (now - prev[1]) / self.ncpu * 100 if prev and now > prev[1] else 0.0
                rss = info["memory_info"].rss if info["memory_info"] else 0
                threads = int(info["num_threads"] or 0)
                handles = int(info["num_handles"] or 0)
                threads_total += threads
                handles_total += handles
                out.append(Proc(
                    short(info["name"] or "?", 22), pid, pct, rss, threads, handles,
                    float(info["create_time"] or 0.0),
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError):
                continue
        self._prev_cpu = seen
        out.sort(key=lambda x: (x.cpu, x.rss), reverse=True)
        return out[:limit], threads_total, handles_total


class SystemPanel(Widget):
    DEFAULT_CSS = """
    SystemPanel { width: 1fr; height: 1fr; }
    """

    can_focus = True

    def __init__(self, sampler: Sampler | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sampler = sampler or Sampler()
        self.sort_key = "cpu"
        self.cursor = 0
        self.pending_kill: int | None = None
        self.message: tuple[str, float] | None = None

    def on_mount(self) -> None:
        self.sampler.fast()
        self._slow()
        self.set_interval(1.0, self._fast)
        self.set_interval(4.0, self._slow)
        self.focus()

    def _fast(self) -> None:
        self.sampler.fast()
        self.refresh()

    @work(thread=True, exclusive=True)
    def _slow(self) -> None:
        self.sampler.slow()
        self.app.call_from_thread(self.refresh)

    # -- interactions ---------------------------------------------------
    def on_key(self, event) -> None:
        key = event.key
        procs = self._sorted_procs()
        if key in ("up", "down"):
            if self.pending_kill is not None or not procs:
                return
            step = -1 if key == "up" else 1
            self.cursor = max(0, min(len(procs) - 1, self.cursor + step))
        elif key == "s":
            order = ["cpu", "mem", "pid", "name"]
            self.sort_key = order[(order.index(self.sort_key) + 1) % len(order)]
            self.cursor = 0
        elif key == "k":
            if procs:
                self.pending_kill = procs[min(self.cursor, len(procs) - 1)].pid
        elif key == "enter" and self.pending_kill is not None:
            self._kill(self.pending_kill)
            self.pending_kill = None
        elif key == "escape":
            self.pending_kill = None
        else:
            return
        event.stop()
        self.refresh()

    def _kill(self, pid: int) -> None:
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            self.message = (f"已结束 {name} ({pid})", time.monotonic())
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
            self.message = (f"结束失败: {exc}", time.monotonic())
        self._slow()

    def _sorted_procs(self) -> list[Proc]:
        procs = list(self.sampler.state.procs)
        match self.sort_key:
            case "mem":
                procs.sort(key=lambda p: p.rss, reverse=True)
            case "pid":
                procs.sort(key=lambda p: p.pid)
            case "name":
                procs.sort(key=lambda p: p.name.lower())
            case _:
                procs.sort(key=lambda p: p.cpu, reverse=True)
        return procs

    # -- rendering ------------------------------------------------------
    def build(self, w: int, h: int) -> Text:
        if h >= 48 and w >= 70:
            return self._top_bottom(w, h)
        if w >= 80 and h >= 26:
            return self._two_columns(w, h)
        return self._one_column(w, h)

    def render(self) -> Text:
        w, h = self.content_size
        if w < 20 or h < 6:
            return Text("")
        return self.build(w, h)

    def _top_bottom(self, w: int, h: int) -> Text:
        """Tall screens: hardware cards on top, full-width process table below."""
        col = (w - 3) // 2
        sections = [
            ("cpu", self._sec_cpu(col)),
            ("mem", self._sec_mem(col)),
            ("sys", self._sec_sys(col)),
            ("net", self._sec_net(col)),
            ("gpu", self._sec_gpu(col)),
            ("disk", self._sec_disk(col)),
        ]
        left: list[Text] = []
        right: list[Text] = []
        for _, block in sections:
            if len(left) <= len(right):
                left += block + [Text("")]
            else:
                right += block + [Text("")]
        top = self._merge_columns(left, right, col, 3)
        table = self._sec_proc(w, rows=max(6, h - len(top) - 2))
        return self._finish(top + [Text("")] + table, h)

    def _two_columns(self, w: int, h: int) -> Text:
        gap = 3
        col = (w - gap) // 2
        left = self._sec_cpu(col) + [Text("")] + self._sec_mem(col) + [Text("")] + \
            self._sec_disk(col) + [Text("")] + self._sec_sys(col)
        right = self._sec_gpu(col) + [Text("")] + self._sec_net(col) + [Text("")] + \
            self._sec_proc(col, rows=max(6, h - 24))
        return self._finish(self._merge_columns(left, right, col, gap), h)

    def _one_column(self, w: int, h: int) -> Text:
        proc_rows = max(5, min(10, h - 22))
        proc_block = self._sec_proc(w, rows=proc_rows)
        budget = h - len(proc_block) - 1
        lines: list[Text] = []
        for block in (self._sec_cpu(w, compact=True), self._sec_mem(w), self._sec_gpu(w, compact=True),
                      self._sec_net(w), self._sec_disk(w), self._sec_sys(w)):
            if len(lines) + len(block) + 1 > budget:
                break
            lines += block + [Text("")]
        lines += proc_block
        return self._finish(lines, h)

    def _finish(self, lines: list[Text], h: int) -> Text:
        out = Text(no_wrap=True, end="")
        for i, line in enumerate(lines):
            if i >= h:
                break
            out.append_text(line)
            out.append("\n")
        return out

    def _merge_columns(self, left: list[Text], right: list[Text], col: int, gap: int) -> list[Text]:
        sep = Text(" │ ", style=theme.hexc(theme.mix(theme.P.dim, theme.P.bg, 0.4)))
        rows: list[Text] = []
        for i in range(max(len(left), len(right))):
            row = self._pad(left[i] if i < len(left) else Text(""), col)
            if right:
                row.append_text(sep)
                row.append_text(self._pad(right[i] if i < len(right) else Text(""), col))
            rows.append(row)
        return rows

    @staticmethod
    def _pad(text: Text, width: int) -> Text:
        padded = text.copy()
        missing = width - cell_len(text.plain)
        if missing > 0:
            padded.append(" " * missing)
        elif missing < 0:
            padded = text.copy()
            padded.truncate(width)
        return padded

    # -- sections -------------------------------------------------------
    def _style(self) -> dict[str, str]:
        p = theme.P
        return {
            "dim": theme.hexc(p.dim), "text": theme.hexc(p.text), "cyan": theme.hexc(p.cyan),
            "mag": theme.hexc(p.magenta), "pur": theme.hexc(p.purple), "amb": theme.hexc(p.amber),
            "green": theme.hexc(p.green), "red": theme.hexc(p.red),
            "rule": theme.hexc(theme.mix(p.dim, p.panel, 0.4)),
        }

    def _header(self, title: str, w: int, extra: str = "") -> Text:
        c = self._style()
        line = Text(no_wrap=True, end="")
        line.append("◤ ", c["cyan"])
        line.append(title, f"bold {c['cyan']}")
        if extra:
            line.append("  " + extra, c["dim"])
        return line

    def _bar(self, value: float, width: int, stops, suffix: str = "", style: str | None = None) -> Text:
        c = self._style()
        line = Text(no_wrap=True, end="")
        for ch, color in theme.gauge(value, max(4, width), stops):
            line.append(ch, color)
        if suffix:
            line.append(" " + suffix, style or c["text"])
        return line

    def _sec_cpu(self, w: int, compact: bool = False) -> list[Text]:
        c = self._style()
        s = self.sampler.state
        lines = [self._header("CPU", w)]
        name = self.sampler.cpu_name.replace("(R)", "").replace("(TM)", "").replace("CPU ", "")
        lines.append(Text(short(name, w - 2), style=c["text"]))
        spec = f"{self.sampler.cores}C/{self.sampler.ncpu}T"
        if s.freq:
            spec += f" · {s.freq:.2f}GHz"
        lines.append(Text(" " + spec, style=c["dim"]))
        bar_w = max(6, w - 9)
        lines.append(self._bar(s.cpu / 100, bar_w, [theme.P.cyan, theme.P.purple, theme.P.magenta],
                               f"{s.cpu:4.1f}%"))
        if not compact:
            spark = Text(" ", no_wrap=True)
            spark.append(theme.sparkline(list(self.sampler.cpu_hist), bar_w), c["cyan"])
            spark.append(" 60s", c["dim"])
            lines.append(spark)

        n = len(s.per_core)
        if n:
            cols = (8 if w >= 46 else 4) if compact else (2 if w < 50 else 4)
            cell_w = max(2, (w - 1) // cols - 3)
            for start in range(0, n, cols):
                row = Text(no_wrap=True, end="")
                for i in range(start, min(start + cols, n)):
                    row.append(f"{i:>2}", theme.hexc(theme.mix(theme.P.dim, theme.P.panel, 0.1)))
                    for ch, color in theme.gauge(s.per_core[i] / 100, cell_w,
                                                 [theme.P.cyan, theme.P.purple, theme.P.magenta]):
                        row.append(ch, color)
                    row.append(" ")
                lines.append(row)
        return lines

    def _sec_mem(self, w: int) -> list[Text]:
        c = self._style()
        s = self.sampler.state
        lines = [self._header("MEM", w)]
        value = Text(no_wrap=True, end="")
        value.append(f"{theme.fmt_bytes(s.mem_used)} / {theme.fmt_bytes(s.mem_total)}", c["text"])
        value.append(f"  {s.mem_pct:.0f}%", f"bold {c['mag']}")
        lines.append(value)
        lines.append(self._bar(s.mem_pct / 100, max(6, w - 2), [theme.P.cyan, theme.P.blue, theme.P.magenta]))
        swap_pct = s.swap_used / s.swap_total if s.swap_total else 0.0
        sw = Text(no_wrap=True, end="")
        sw.append("SWAP ", c["dim"])
        for ch, color in theme.gauge(swap_pct, max(4, w - 22), [theme.P.purple, theme.P.magenta]):
            sw.append(ch, color)
        sw.append(f" {theme.fmt_bytes(s.swap_used)}/{theme.fmt_bytes(s.swap_total)}", c["dim"])
        lines.append(sw)
        return lines

    def _sec_gpu(self, w: int, compact: bool = False) -> list[Text]:
        c = self._style()
        s = self.sampler.state
        g = s.gpu
        lines = [self._header("GPU", w)]
        if not g:
            text = " 采样中…" if not self.sampler.loaded else " 集成显卡 / nvidia-smi 不可用"
            lines.append(Text(text, style=c["dim"]))
            return lines
        info = Text(no_wrap=True, end="")
        info.append(f" {g.util:3.0f}%", f"bold {c['mag']}")
        info.append(f"  {g.mem_used / 1024:.1f}/{g.mem_total / 1024:.1f}G", c["dim"])
        info.append(f"  {g.temp:.0f}°C", c["amb"])
        if g.fan is not None:
            info.append(f"  {g.fan:.0f}rpm", c["dim"])
        if compact:
            lines.append(Text(" " + short(g.name, max(6, w - 2)), style=c["text"]))
            lines.append(info)
            lines.append(self._bar(g.util / 100, max(6, w - 2),
                                   [theme.P.magenta, theme.P.red, theme.P.amber]))
            return lines
        lines.append(Text(" " + short(g.name, w - 2), style=c["text"]))
        lines.append(info)
        lines.append(self._bar(g.util / 100, max(6, w - 2),
                               [theme.P.magenta, theme.P.red, theme.P.amber]))
        vram = Text(no_wrap=True, end="")
        vram.append("VRAM ", c["dim"])
        ratio = g.mem_used / g.mem_total if g.mem_total else 0.0
        for ch, color in theme.gauge(ratio, max(4, w - 20), [theme.P.purple, theme.P.cyan]):
            vram.append(ch, color)
        vram.append(f" {g.power:.0f}W", c["dim"])
        if g.power_limit:
            vram.append(f"/{g.power_limit:.0f}W", c["dim"])
        lines.append(vram)
        clocks = Text(no_wrap=True, end="")
        clocks.append(f" GFX {g.clock_gfx:.0f}MHz  MEM {g.clock_mem:.0f}MHz", c["dim"])
        lines.append(clocks)
        if g.enc or g.dec:
            codec = Text(no_wrap=True, end="")
            codec.append(f" ENC {g.enc:.0f}%  DEC {g.dec:.0f}%", c["dim"])
            lines.append(codec)
        if len(self.sampler.gpu_hist) > 2:
            spark = Text(no_wrap=True, end="")
            spark.append(" " + theme.sparkline(list(self.sampler.gpu_hist), max(4, w - 6)), c["mag"])
            spark.append(" 60s", c["dim"])
            lines.append(spark)
        return lines

    def _sec_net(self, w: int) -> list[Text]:
        c = self._style()
        s = self.sampler.state
        lines = [self._header("NET", w)]
        rate = Text(no_wrap=True, end="")
        rate.append(" ↓ ", c["cyan"])
        rate.append(theme.fmt_rate(s.down), c["text"])
        rate.append("  ↑ ", c["mag"])
        rate.append(theme.fmt_rate(s.up), c["text"])
        lines.append(rate)
        spark = Text(no_wrap=True, end="")
        spark.append(" " + theme.sparkline(list(self.sampler.net_hist), max(4, w - 6)), c["pur"])
        spark.append(" 60s", c["dim"])
        lines.append(spark)
        for nic in s.nics[:2]:
            row = Text(no_wrap=True, end="")
            row.append(" " + short(nic.name, 10), c["text"])
            row.append(f" {nic.speed:.0f}M", c["dim"])
            if nic.ipv4:
                row.append(f"  {nic.ipv4}", c["dim"])
            lines.append(row)
        return lines

    def _sec_disk(self, w: int) -> list[Text]:
        c = self._style()
        s = self.sampler.state
        lines = [self._header("DISK", w)]
        for d in s.disks[:3]:
            pct = d.used / d.total if d.total else 0.0
            row = Text(no_wrap=True, end="")
            row.append(f"{d.mount:<4}", c["dim"])
            for ch, color in theme.gauge(pct, max(4, w - 20), [theme.P.cyan, theme.P.purple, theme.P.magenta]):
                row.append(ch, color)
            row.append(f" {theme.fmt_bytes(d.total - d.used)} free", c["dim"])
            lines.append(row)
        for io in s.disk_ios[:2]:
            row = Text(no_wrap=True, end="")
            row.append(" " + short(io.label, 14), c["dim"])
            row.append(f" R {theme.fmt_rate(io.read)}", c["text"])
            row.append(f" W {theme.fmt_rate(io.write)}", c["dim"])
            lines.append(row)
        return lines

    def _sec_sys(self, w: int) -> list[Text]:
        c = self._style()
        s = self.sampler.state
        lines = [self._header("SYS", w)]
        if s.acpi_temp is not None:
            row = Text(no_wrap=True, end="")
            row.append(" ACPI ", c["dim"])
            row.append(f"{s.acpi_temp:.0f}°C", c["amb"])
            row.append("  (主板热区)", c["dim"])
            lines.append(row)
        row = Text(no_wrap=True, end="")
        row.append(f" 线程 {s.threads_total}  句柄 {s.handles_total / 1000:.0f}k", c["dim"])
        lines.append(row)
        row = Text(no_wrap=True, end="")
        row.append(f" CTX {s.ctx_switches / 1000:.0f}k/s", c["dim"])
        row.append(f"  提交 {theme.fmt_bytes(s.swap_used)}", c["dim"])
        lines.append(row)
        if s.boot_time:
            row = Text(no_wrap=True, end="")
            row.append(f" 开机 {datetime.fromtimestamp(s.boot_time):%m-%d %H:%M}", c["dim"])
            if s.battery:
                pct, plugged, left = s.battery
                row.append(f"  电池 {pct:.0f}%", c["green"] if pct > 40 else c["amb"])
                if left > 0:
                    row.append(f" {left // 3600}h{left % 3600 // 60:02d}m", c["dim"])
                elif plugged:
                    row.append(" AC", c["dim"])
            lines.append(row)
        return lines

    def _sec_proc(self, w: int, rows: int) -> list[Text]:
        c = self._style()
        procs = self._sorted_procs()
        total = len(procs)
        rows = max(3, min(rows, total or 1))
        if self.cursor >= total:
            self.cursor = max(0, total - 1)

        name_w = max(8, w - 15)
        arrow = {"cpu": "CPU%▾", "mem": "MEM▾", "pid": "PID▾", "name": "NAME▾"}[self.sort_key]
        head = Text(no_wrap=True, end="")
        head.append("◤ ", c["cyan"])
        head.append("PROC", f"bold {c['cyan']}")
        head.append(" " * max(1, w - 13 - len(arrow)), "")
        head.append(arrow, c["dim"])
        head.append("  MEM", c["dim"])
        lines = [head]

        start = max(0, min(self.cursor - rows + 1, total - rows)) if total > rows else 0
        if not total:
            lines.append(Text(" 采样中…", style=c["dim"]))
        for i in range(start, min(start + rows, total)):
            proc = procs[i]
            selected = i == self.cursor
            row = Text(no_wrap=True, end="")
            row.append("▌" if selected else " ", c["cyan"] if selected else "")
            name = short(proc.name, name_w)
            row.append(f"{name:<{name_w}}", f"bold {c['text']}" if selected else c["text"])
            row.append(f"{proc.cpu:6.1f}", f"bold {c['mag']}" if selected else c["mag"])
            row.append(f" {theme.fmt_bytes(proc.rss):>6}", c["dim"])
            if selected:
                row.stylize(f"on {theme.hexc(theme.mix(theme.P.cyan, theme.P.panel, 0.16))}")
            lines.append(row)

        detail = Text(no_wrap=True, end="")
        if procs and self.cursor < len(procs):
            proc = procs[self.cursor]
            detail.append(f" {proc.pid} · {proc.threads} thr · {proc.handles} h", c["dim"])
            if proc.created:
                detail.append(f" · {datetime.fromtimestamp(proc.created):%H:%M}", c["dim"])
        lines.append(detail)

        status = Text(no_wrap=True, end="")
        if self.pending_kill is not None:
            target = next((p for p in procs if p.pid == self.pending_kill), None)
            label = f"{target.name} ({target.pid})" if target else str(self.pending_kill)
            status.append(f" 结束 {label}? ", f"bold {c['amb']}")
            status.append("Enter 确认 · Esc 取消", c["dim"])
        elif self.message and time.monotonic() - self.message[1] < 4:
            status.append(" " + self.message[0], c["green"])
        else:
            status.append(" ↑↓ 选择 · S 排序 · K 结束", c["dim"])
        lines.append(status)
        return lines


