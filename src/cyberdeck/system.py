"""Hardware monitor: psutil + nvidia-smi sampling and the right-hand panel."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field

import psutil
from rich.text import Text
from textual import work
from textual.widget import Widget

from . import theme

IS_WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if IS_WIN else 0


@dataclass
class Gpu:
    name: str
    util: float
    mem_used: int  # MiB
    mem_total: int
    temp: float
    power: float


@dataclass
class Proc:
    name: str
    pid: int
    cpu: float
    rss: int


@dataclass
class Disk:
    mount: str
    used: int
    total: int


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
    gpu: Gpu | None = None
    disks: list[Disk] = field(default_factory=list)
    procs: list[Proc] = field(default_factory=list)
    battery: tuple[float, bool] | None = None
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


def _gpu_sample() -> Gpu | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, creationflags=NO_WINDOW,
        ).stdout.strip().splitlines()
        if not out:
            return None
        parts = [s.strip() for s in out[0].split(",")]
        return Gpu(
            name=parts[0].replace("NVIDIA ", "").replace(" Laptop GPU", ""),
            util=float(parts[1]), mem_used=int(float(parts[2])), mem_total=int(float(parts[3])),
            temp=float(parts[4]), power=float(parts[5]) if parts[5] not in ("[N/A]", "") else 0.0,
        )
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class Sampler:
    def __init__(self) -> None:
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        self.ncpu = psutil.cpu_count(logical=True) or 1
        self.state = State()
        self.cpu_hist: deque[float] = deque(maxlen=72)
        self.net_hist: deque[float] = deque(maxlen=72)
        self.gpu_hist: deque[float] = deque(maxlen=72)
        self.cpu_name = cpu_model()
        self.cores = psutil.cpu_count(logical=False) or 1
        self._prev_net = psutil.net_io_counters()
        self._prev_disk = psutil.disk_io_counters()
        self._prev_t = time.monotonic()
        self._prev_cpu: dict[int, tuple[float, float]] = {}
        self._stat = psutil.cpu_freq()
        self._slow_t = 0.0

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
        net = psutil.net_io_counters()
        dt = max(1e-3, now - self._prev_t)
        s.down = max(0.0, (net.bytes_recv - self._prev_net.bytes_recv) / dt)
        s.up = max(0.0, (net.bytes_sent - self._prev_net.bytes_sent) / dt)
        io = psutil.disk_io_counters()
        if io and self._prev_disk:
            s.disk_read = max(0.0, (io.read_bytes - self._prev_disk.read_bytes) / dt)
            s.disk_write = max(0.0, (io.write_bytes - self._prev_disk.write_bytes) / dt)
        self._prev_disk = io or self._prev_disk
        self._prev_net, self._prev_t = net, now
        self.net_hist.append(s.down + s.up)

        s.uptime = time.time() - psutil.boot_time()
        bat = psutil.sensors_battery()
        s.battery = (bat.percent, bat.power_plugged) if bat else None
        return s

    # -- slow (every ~3 s) --------------------------------------------------
    def slow(self) -> State:
        s = self.state
        if time.monotonic() - self._slow_t < 1.5:
            return s
        self._slow_t = time.monotonic()

        s.gpu = _gpu_sample()
        self.gpu_hist.append(s.gpu.util if s.gpu else 0.0)
        s.disks = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            s.disks.append(Disk(part.device.rstrip("\\") or part.mountpoint, u.used, u.total))
        s.procs = self._top_procs()
        return s

    def _top_procs(self, limit: int = 10) -> list[Proc]:
        now = time.monotonic()
        out: list[Proc] = []
        seen: dict[int, tuple[float, float]] = {}
        for p in psutil.process_iter(["pid", "name", "cpu_times", "memory_info"]):
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
                out.append(Proc((info["name"] or "?")[:22], pid, pct, rss))
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError):
                continue
        self._prev_cpu = seen
        out.sort(key=lambda x: (x.cpu, x.rss), reverse=True)
        return out[:limit]


class SystemPanel(Widget):
    DEFAULT_CSS = """
    SystemPanel { width: 1fr; height: 1fr; }
    """

    def __init__(self, sampler: Sampler | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sampler = sampler or Sampler()

    def on_mount(self) -> None:
        self.sampler.fast()
        self.set_interval(0.7, self._fast)
        self.set_interval(2.5, self._slow)

    def _fast(self) -> None:
        self.sampler.fast()
        self.refresh()

    @work(thread=True, exclusive=True)
    def _slow(self) -> None:
        self.sampler.slow()
        self.app.call_from_thread(self.refresh)

    # ------------------------------------------------------------------
    def build(self, w: int, h: int) -> Text:
        p = theme.P
        s = self.sampler.state
        out = Text(no_wrap=True, end="")
        pad = 1
        iw = max(20, w - pad * 2)

        def line(*parts: tuple[str, str]) -> None:
            out.append(" " * pad)
            for text, style in parts:
                out.append(text, style)

        def rule() -> None:
            line(("─" * iw, theme.hexc(theme.mix(p.dim, p.panel, 0.4))))

        dim = theme.hexc(p.dim)
        txt = theme.hexc(p.text)
        cyan = theme.hexc(p.cyan)
        mag = theme.hexc(p.magenta)
        pur = theme.hexc(p.purple)

        # ---- CPU -------------------------------------------------------
        line(("◤ ", cyan), ("CPU  ", f"bold {cyan}"))
        name = self.sampler.cpu_name.replace("(R)", "").replace("(TM)", "").replace("CPU ", "")
        line((name[: iw - 4], txt))
        out.append("\n")
        line((f" {self.sampler.cores}C/{self.sampler.ncpu}T", dim))
        if s.freq:
            line((f" · {s.freq:4.2f} GHz", dim))
        out.append("\n")

        bar_w = max(12, iw - 8)
        line((" ", ""))
        for ch, color in theme.gauge(s.cpu / 100, bar_w, [p.cyan, p.purple, p.magenta]):
            out.append(ch, color)
        line((f" {s.cpu:4.1f}%", f"bold {txt}"))
        out.append("\n")

        # sparkline
        line((" ", ""), (theme.sparkline(list(self.sampler.cpu_hist), bar_w), theme.hexc(p.cyan)),
             (" 60s", dim))
        out.append("\n")

        # per-core grid
        n = len(s.per_core)
        if n:
            cols = 4 if iw < 46 else 8
            cell_w = max(3, iw // cols - 4)
            for r in range(0, n, cols):
                line((" ", ""))
                for i in range(r, min(r + cols, n)):
                    v = s.per_core[i] / 100
                    out.append(f"{i:>2}", theme.hexc(theme.mix(p.dim, p.panel, 0.15)))
                    for ch, color in theme.gauge(v, cell_w, [p.cyan, p.purple, p.magenta]):
                        out.append(ch, color)
                    out.append(" ")
                out.append("\n")

        rule()
        out.append("\n\n")

        # ---- MEM -------------------------------------------------------
        line(("◤ ", cyan), ("MEM  ", f"bold {cyan}"))
        line((f"{theme.fmt_bytes(s.mem_used)} / {theme.fmt_bytes(s.mem_total)}", txt))
        line((f"  {s.mem_pct:4.1f}%", dim))
        out.append("\n")
        line((" ", ""))
        for ch, color in theme.gauge(s.mem_pct / 100, bar_w, [p.cyan, p.blue, p.magenta]):
            out.append(ch, color)
        out.append("\n")

        swap_pct = s.swap_used / s.swap_total if s.swap_total else 0.0
        line((" SWAP ", dim))
        for ch, color in theme.gauge(swap_pct, max(6, bar_w - 14), [p.purple, p.magenta]):
            out.append(ch, color)
        line((f" {theme.fmt_bytes(s.swap_used)}/{theme.fmt_bytes(s.swap_total)}", dim))
        out.append("\n")

        # ---- GPU -------------------------------------------------------
        g = s.gpu
        line(("◤ ", cyan), ("GPU  ", f"bold {cyan}"))
        if g:
            line((g.name[: max(8, iw - 30)], txt))
            line((f"  {g.util:3.0f}%", mag), (f"  {g.mem_used / 1024:.1f}/{g.mem_total / 1024:.1f}G", dim),
                 (f"  {g.temp:.0f}°C", theme.hexc(p.amber)))
            out.append("\n")
            line((" ", ""))
            for ch, color in theme.gauge(g.util / 100, bar_w, [p.magenta, p.red, p.amber]):
                out.append(ch, color)
            out.append("\n")
            gpu_mem = g.mem_used / g.mem_total if g.mem_total else 0.0
            line((" VRAM ", dim))
            for ch, color in theme.gauge(gpu_mem, max(6, bar_w - 14), [p.purple, p.cyan]):
                out.append(ch, color)
            line((f" {g.power:.0f} W", dim))
            out.append("\n")
            if len(self.sampler.gpu_hist) > 2:
                line(("  ", ""), (theme.sparkline(list(self.sampler.gpu_hist), bar_w - 8), mag),
                     (" 60s", dim))
                out.append("\n")
        else:
            line(("集成显卡 / nvidia-smi 不可用", dim))
            out.append("\n")

        rule()
        out.append("\n\n")

        # ---- NET -------------------------------------------------------
        line(("◤ ", cyan), ("NET  ", f"bold {cyan}"))
        line(("↓ ", theme.hexc(p.cyan)), (theme.fmt_rate(s.down), txt))
        line(("   ↑ ", theme.hexc(p.magenta)), (theme.fmt_rate(s.up), txt))
        out.append("\n")
        line((" ", ""), (theme.sparkline(list(self.sampler.net_hist), bar_w - 8), pur), (" 60s", dim))
        out.append("\n")
        line((" DISK ", dim), ("R ", dim), (theme.fmt_rate(s.disk_read), txt),
             ("   W ", dim), (theme.fmt_rate(s.disk_write), txt))
        out.append("\n")

        # ---- DISK ------------------------------------------------------
        for d in s.disks[:3]:
            pct = d.used / d.total if d.total else 0
            free = d.total - d.used
            line((f" {d.mount:<4}", dim))
            dw = max(6, bar_w - 22)
            for ch, color in theme.gauge(pct, dw, [p.cyan, p.purple, p.magenta]):
                out.append(ch, color)
            line((f" {theme.fmt_bytes(free)} free", dim))
            out.append("\n")

        rule()
        out.append("\n\n")

        # ---- PROCS -----------------------------------------------------
        name_w = max(6, iw - 22)
        line(("◤ ", cyan), ("TOP", f"bold {cyan}"))
        line((" " * max(1, name_w - 4), ""), ("CPU%", dim), ("     ", ""), ("MEM", dim))
        out.append("\n")
        for proc in s.procs[:10]:
            nm = proc.name[:name_w]
            line((f" {nm:<{name_w}}", txt))
            line((f"{proc.cpu:6.1f}", mag), (f"  {theme.fmt_bytes(proc.rss):>6}", dim))
            out.append("\n")

        # ---- footer ----------------------------------------------------
        foot = Text(no_wrap=True, end="")
        foot.append(f" UPTIME {theme.fmt_uptime(s.uptime)}", dim)
        if s.battery:
            pct, plugged = s.battery
            foot.append("   BAT ", dim)
            foot.append(f"{pct:.0f}%", theme.hexc(p.green if pct > 40 else p.amber))
            foot.append(" AC" if plugged else "", dim)
        out.append_text(foot)

        return out

    def render(self) -> Text:
        w, h = self.content_size
        if w < 20 or h < 6:
            return Text("")
        return self.build(w, h)



