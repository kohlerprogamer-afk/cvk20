#!/usr/bin/env python3
"""System Diagnostic Tool — cross-platform desktop GUI built with CustomTkinter."""

import customtkinter as ctk
import psutil
import platform
import subprocess
import shutil
import threading
import time
import socket
import re
import queue
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    import cpuinfo
    HAS_CPUINFO = True
except ImportError:
    HAS_CPUINFO = False

# ─────────────────────────── appearance ────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ─────────────────────────── constants ─────────────────────────────
STATUS_FG: dict[str, str] = {
    "OK":       "#2ecc71",
    "WARNING":  "#f39c12",
    "CRITICAL": "#e74c3c",
    "UNKNOWN":  "#95a5a6",
}
STATUS_BG: dict[str, tuple] = {
    "OK":       ("#d4edda", "#0e2a1a"),
    "WARNING":  ("#fff3cd", "#2a1f00"),
    "CRITICAL": ("#f8d7da", "#2a0808"),
    "UNKNOWN":  ("#e2e3e5", "#1c1c2a"),
}
STATUS_ICON: dict[str, str] = {
    "OK":       "✓",
    "WARNING":  "⚠",
    "CRITICAL": "✗",
    "UNKNOWN":  "?",
}
CARD_ICONS: dict[str, str] = {
    "CPU":           "⚡",
    "Memory":        "▣",
    "Disk":          "◉",
    "Network":       "◈",
    "Processes":     "⚙",
    "System Health": "♥",
}


# ───────────────────────── data model ──────────────────────────────
@dataclass
class CheckResult:
    name: str
    status: str = "UNKNOWN"
    metrics: dict = field(default_factory=dict)
    issues: list  = field(default_factory=list)
    fixes: list   = field(default_factory=list)


def _fmt_bytes(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _extract_pct(value: str) -> Optional[float]:
    """Return 0.0–1.0 if the value string encodes a percentage, else None."""
    m = re.search(r'\((\d+\.?\d*)%\)', value)
    if m:
        return min(float(m.group(1)) / 100, 1.0)
    m = re.match(r'^(\d+\.?\d*)%$', value.strip())
    if m:
        return min(float(m.group(1)) / 100, 1.0)
    return None


def _pct_bar_color(pct: float) -> str:
    if pct >= 0.90:
        return STATUS_FG["CRITICAL"]
    if pct >= 0.75:
        return STATUS_FG["WARNING"]
    return "#4fc3f7"


# ─────────────────────── diagnostic engine ─────────────────────────
class SystemDiagnostics:
    """All diagnostic checks live here; each returns a CheckResult."""

    # ── CPU ──────────────────────────────────────────────────────────
    def check_cpu(self) -> CheckResult:
        r = CheckResult("CPU", "OK")

        if HAS_CPUINFO:
            try:
                r.metrics["Model"] = cpuinfo.get_cpu_info().get("brand_raw", "Unknown")
            except Exception:
                r.metrics["Model"] = platform.processor() or "Unknown"
        else:
            r.metrics["Model"] = platform.processor() or "Unknown"

        r.metrics["Physical Cores"] = str(psutil.cpu_count(logical=False) or "N/A")
        r.metrics["Logical Cores"]  = str(psutil.cpu_count(logical=True)  or "N/A")

        freq = psutil.cpu_freq()
        r.metrics["Clock Speed"] = f"{freq.current:.0f} MHz" if freq else "N/A"
        if freq and freq.max:
            r.metrics["Max Clock"] = f"{freq.max:.0f} MHz"

        usage = psutil.cpu_percent(interval=1)
        r.metrics["Current Usage"] = f"{usage:.1f}%"

        if usage > 80:
            r.issues.append(f"High CPU usage: {usage:.1f}% (threshold: 80%)")
            r.status = "CRITICAL" if usage > 90 else "WARNING"
            r.fixes.append(
                "Open Task Manager (Ctrl+Shift+Esc) → Processes tab → sort by CPU → "
                "right-click and End Task on anything you don't need."
            )
            r.fixes.append(
                "Check Startup apps: Settings → Apps → Startup — disable anything "
                "you don't need running at login."
            )

        try:
            all_temps = psutil.sensors_temperatures()
            if all_temps:
                cpu_temp: Optional[float] = None
                for key in ("coretemp", "cpu_thermal", "k10temp", "cpu-thermal", "acpitz"):
                    if key in all_temps and all_temps[key]:
                        cpu_temp = max(e.current for e in all_temps[key])
                        break
                if cpu_temp is None:
                    for readings in all_temps.values():
                        if readings:
                            cpu_temp = max(e.current for e in readings)
                            break
                if cpu_temp is not None:
                    r.metrics["Temperature"] = f"{cpu_temp:.1f} °C"
                    if cpu_temp > 85:
                        r.issues.append(f"High CPU temperature: {cpu_temp:.1f}°C (threshold: 85°C)")
                        if r.status != "CRITICAL":
                            r.status = "CRITICAL" if cpu_temp > 95 else "WARNING"
                        r.fixes.append(
                            "Clean dust from your CPU cooler and case vents with compressed air. "
                            "Ensure all case fans are spinning. If the problem persists, "
                            "consider reapplying thermal paste between the CPU and heatsink."
                        )
                else:
                    r.metrics["Temperature"] = "N/A"
            else:
                r.metrics["Temperature"] = "N/A (no sensors)"
        except (AttributeError, OSError):
            r.metrics["Temperature"] = "N/A"

        return r

    # ── Memory ───────────────────────────────────────────────────────
    def check_memory(self) -> CheckResult:
        r = CheckResult("Memory", "OK")

        try:
            ram = psutil.virtual_memory()
            r.metrics["Total RAM"]  = _fmt_bytes(ram.total)
            r.metrics["Used RAM"]   = _fmt_bytes(ram.used)
            r.metrics["Available"]  = _fmt_bytes(ram.available)
            r.metrics["RAM Usage"]  = f"{ram.percent:.1f}%"

            if ram.percent > 85:
                r.issues.append(f"High RAM usage: {ram.percent:.1f}% (threshold: 85%)")
                r.status = "CRITICAL" if ram.percent > 95 else "WARNING"
                r.fixes.append(
                    "Close unused browser tabs and applications. "
                    "Open Task Manager (Ctrl+Shift+Esc) → Memory column to find "
                    "the biggest consumers and close or restart them."
                )
                r.fixes.append(
                    "Disable memory-heavy startup programs: "
                    "Settings → Apps → Startup, or Task Manager → Startup Apps tab."
                )
        except Exception as e:
            r.metrics["RAM"] = f"Read error: {e}"
            r.status = "UNKNOWN"

        try:
            swap = psutil.swap_memory()
            r.metrics["Total Swap"] = _fmt_bytes(swap.total)
            r.metrics["Swap Used"]  = _fmt_bytes(swap.used)
            r.metrics["Swap Usage"] = f"{swap.percent:.1f}%"

            if swap.total > 0 and swap.percent > 50:
                r.issues.append(f"High swap/page-file usage: {swap.percent:.1f}% (threshold: 50%)")
                if r.status == "OK":
                    r.status = "WARNING"
                r.fixes.append(
                    "Windows: increase your page file — "
                    "Search 'Adjust the appearance and performance of Windows' → Advanced → "
                    "Virtual Memory → Change → set a larger custom size. "
                    "Long-term fix: install more physical RAM."
                )
        except Exception as e:
            r.metrics["Swap"] = f"Read error: {e}"

        return r

    # ── Disk ─────────────────────────────────────────────────────────
    def check_disk(self) -> CheckResult:
        r = CheckResult("Disk", "OK")

        for part in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(part.mountpoint)
                r.metrics[part.device] = (
                    f"{_fmt_bytes(u.used)} / {_fmt_bytes(u.total)}  ({u.percent:.1f}%)"
                )
                if u.percent > 90:
                    r.issues.append(
                        f"{part.device} is {u.percent:.1f}% full "
                        f"({_fmt_bytes(u.free)} free)"
                    )
                    if r.status == "OK":
                        r.status = "CRITICAL" if u.percent > 95 else "WARNING"
                    r.fixes.append(
                        f"Free space on {part.device}: "
                        "run Disk Cleanup (Win+R → cleanmgr), "
                        "empty the Recycle Bin, delete files in C:\\Windows\\Temp, "
                        "and go to Settings → Apps to uninstall programs you no longer use."
                    )
            except (PermissionError, OSError):
                r.metrics[part.device] = "Permission denied"

        if shutil.which("smartctl"):
            try:
                scan = subprocess.run(
                    ["smartctl", "--scan"], capture_output=True, text=True, timeout=5
                )
                if scan.returncode == 0:
                    for line in scan.stdout.splitlines():
                        dev = line.split()[0]
                        try:
                            health = subprocess.run(
                                ["smartctl", "-H", dev],
                                capture_output=True, text=True, timeout=5
                            )
                            if "FAILED" in health.stdout:
                                r.issues.append(f"SMART failure on {dev}")
                                r.status = "CRITICAL"
                                r.fixes.append(
                                    f"SMART failure on {dev}: back up all important files "
                                    "immediately — drive failure may be imminent. "
                                    "Plan to replace this drive as soon as possible."
                                )
                            elif "PASSED" in health.stdout:
                                r.metrics[f"SMART {dev}"] = "PASSED"
                        except Exception:
                            pass
            except Exception:
                pass

        return r

    # ── Network ──────────────────────────────────────────────────────
    def check_network(self) -> CheckResult:
        r = CheckResult("Network", "OK")

        addrs  = psutil.net_if_addrs()
        stats  = psutil.net_if_stats()
        io_all = psutil.net_io_counters(pernic=True)
        active = 0

        for iface, addr_list in addrs.items():
            if iface.startswith("lo"):
                continue
            st = stats.get(iface)
            if not (st and st.isup):
                continue
            ipv4 = [a.address for a in addr_list if a.family == socket.AF_INET]
            if not ipv4:
                continue

            active += 1
            r.metrics[f"{iface} IP"]   = ", ".join(ipv4)
            io = io_all.get(iface)
            if io:
                r.metrics[f"{iface} Sent"] = _fmt_bytes(io.bytes_sent)
                r.metrics[f"{iface} Recv"] = _fmt_bytes(io.bytes_recv)
                if io.errin or io.errout:
                    r.issues.append(f"{iface}: {io.errin} inbound / {io.errout} outbound errors")
                    if r.status == "OK":
                        r.status = "WARNING"
                    r.fixes.append(
                        f"Network errors on {iface}: update your network adapter driver "
                        "via Device Manager → Network Adapters → right-click → Update driver. "
                        "Also try a different Ethernet cable, or switch WiFi bands (2.4 GHz ↔ 5 GHz)."
                    )
                if io.dropin or io.dropout:
                    r.issues.append(f"{iface}: {io.dropin} inbound / {io.dropout} outbound drops")
                    if r.status == "OK":
                        r.status = "WARNING"
                    r.fixes.append(
                        f"Packet drops on {iface}: move closer to your router, "
                        "use a wired Ethernet connection if possible, "
                        "or reduce interference by switching WiFi channels in your router settings."
                    )

        r.metrics["Active Interfaces"] = str(active)
        if active == 0:
            r.issues.append("No active IPv4 interfaces detected")
            r.status = "WARNING"
            r.fixes.append(
                "Check that your network cable is plugged in or WiFi is enabled. "
                "In Windows: Settings → Network & Internet → check adapter status. "
                "Try: ipconfig /release  then  ipconfig /renew  in Command Prompt."
            )

        return r

    # ── Processes ────────────────────────────────────────────────────
    def check_processes(self) -> CheckResult:
        r = CheckResult("Processes", "OK")
        snapshot: list[dict] = []
        zombie = 0

        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                info = proc.info
                snapshot.append(info)
                if info.get("status") == psutil.STATUS_ZOMBIE:
                    zombie += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        time.sleep(0.3)

        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                for s in snapshot:
                    if s["pid"] == info["pid"]:
                        s["cpu_percent"] = info.get("cpu_percent", 0) or 0
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        by_cpu = sorted(snapshot, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:5]
        by_mem = sorted(snapshot, key=lambda x: x.get("memory_percent") or 0, reverse=True)[:5]

        r.metrics["Total Processes"] = str(len(snapshot))
        r.metrics["Zombie Processes"] = str(zombie)

        cpu_str = ", ".join(
            f"{p['name']} ({p.get('cpu_percent', 0):.1f}%)"
            for p in by_cpu if p.get("cpu_percent")
        )
        if cpu_str:
            r.metrics["Top CPU"] = cpu_str

        mem_str = ", ".join(
            f"{p['name']} ({p.get('memory_percent', 0):.1f}%)"
            for p in by_mem if p.get("memory_percent")
        )
        if mem_str:
            r.metrics["Top Memory"] = mem_str

        if zombie > 0:
            r.issues.append(f"{zombie} zombie process(es) found")
            r.status = "WARNING"
            r.fixes.append(
                "Zombie processes are harmless remnants of crashed apps. "
                "Restart the application that created them, or reboot your computer to clear them."
            )

        return r

    # ── System Health ────────────────────────────────────────────────
    def check_system_health(self) -> CheckResult:
        r = CheckResult("System Health", "OK")
        system = platform.system()

        boot = psutil.boot_time()
        uptime = timedelta(seconds=int(time.time() - boot))
        d = uptime.days
        h, rem = divmod(uptime.seconds, 3600)
        m = rem // 60
        r.metrics["Uptime"]    = f"{d}d {h}h {m}m"
        r.metrics["Boot Time"] = datetime.fromtimestamp(boot).strftime("%Y-%m-%d %H:%M:%S")

        if system == "Linux" and shutil.which("systemctl"):
            try:
                out = subprocess.run(
                    ["systemctl", "--failed", "--no-pager", "--plain"],
                    capture_output=True, text=True, timeout=5
                )
                failed = [
                    l for l in out.stdout.splitlines()
                    if l.strip()
                    and not l.startswith("UNIT")
                    and "loaded units" not in l.lower()
                    and "failed" in l.lower()
                ]
                r.metrics["Failed Services"] = str(len(failed)) if failed else "None"
                if failed:
                    r.issues.append(f"{len(failed)} failed systemd service(s)")
                    r.status = "WARNING"
                    r.fixes.append(
                        "Check which services failed: run  systemctl --failed  "
                        "then restart each one with  sudo systemctl restart <service-name>  "
                        "and view logs with  journalctl -xe"
                    )
            except Exception:
                r.metrics["Failed Services"] = "Unknown"

        elif system == "Darwin":
            try:
                out = subprocess.run(
                    ["launchctl", "list"], capture_output=True, text=True, timeout=5
                )
                bad = [
                    l for l in out.stdout.splitlines()
                    if l and not l.startswith("PID") and l.split()[0] not in ("-", "0")
                ]
                r.metrics["Launchd Issues"] = str(len(bad)) if bad else "None"
            except Exception:
                r.metrics["Launchd Issues"] = "Unknown"

        if system == "Linux":
            for cmd, parser in [
                (["apt", "list", "--upgradable"],
                 lambda o: [l for l in o.splitlines() if "[upgradable" in l]),
                (["dnf", "check-update"],
                 lambda o: [l for l in o.splitlines() if l and not l.startswith("Last")]),
                (["yum", "check-update"],
                 lambda o: [l for l in o.splitlines() if l and not l.startswith("Last")]),
            ]:
                if shutil.which(cmd[0]):
                    try:
                        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                        pkgs = parser(out.stdout)
                        r.metrics["Pending Updates"] = f"{len(pkgs)} package(s)" if pkgs else "Up to date"
                        if len(pkgs) > 10:
                            r.issues.append(f"{len(pkgs)} pending OS updates")
                            if r.status == "OK":
                                r.status = "WARNING"
                            r.fixes.append(
                                f"Install {len(pkgs)} pending updates by running: "
                                "sudo apt upgrade  (or  sudo dnf upgrade  /  sudo yum upgrade)."
                            )
                    except Exception:
                        r.metrics["Pending Updates"] = "Unknown"
                    break

        elif system == "Darwin":
            try:
                out = subprocess.run(
                    ["softwareupdate", "-l"], capture_output=True, text=True, timeout=20
                )
                if "No new software available" in out.stdout + out.stderr:
                    r.metrics["Pending Updates"] = "Up to date"
                else:
                    updates = [l for l in out.stdout.splitlines() if l.strip().startswith("*")]
                    if updates:
                        r.metrics["Pending Updates"] = f"{len(updates)} available"
                        r.issues.append(f"{len(updates)} macOS update(s) available")
                        if r.status == "OK":
                            r.status = "WARNING"
                        r.fixes.append(
                            "Install macOS updates: open System Settings → General → "
                            "Software Update and click 'Update Now'."
                        )
            except Exception:
                r.metrics["Pending Updates"] = "Unknown"

        elif system == "Windows":
            r.metrics["Pending Updates"] = "See Windows Update"
            r.fixes.append(
                "Check for Windows updates: Settings → Windows Update → Check for updates. "
                "Keeping Windows updated installs security patches and bug fixes."
            )

        return r


# ─────────────────────────── scoring ───────────────────────────────
def health_score(results: dict[str, CheckResult]) -> int:
    score = 100
    for r in results.values():
        if r.status == "WARNING":
            score -= 10
        elif r.status == "CRITICAL":
            score -= 20
        score -= len(r.issues) * 2
    return max(0, min(100, score))


# ─────────────────────── card widget ───────────────────────────────
class DiagnosticCard(ctk.CTkFrame):
    """Single category result card — full-width, with left accent stripe."""

    def __init__(self, parent, title: str, icon: str = "◈", **kw):
        super().__init__(
            parent,
            corner_radius=14,
            fg_color=("#ffffff", "#16162a"),
            **kw,
        )

        # ── left accent stripe ───────────────────────────────────────
        self._stripe = ctk.CTkFrame(self, width=5, fg_color="#444455", corner_radius=3)
        self._stripe.pack(side="left", fill="y", padx=(5, 0), pady=5)
        self._stripe.pack_propagate(False)

        # ── body ────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=(12, 16), pady=14)

        # header row
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x")

        self._icon_lbl = ctk.CTkLabel(
            hdr, text=icon,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#666688",
            fg_color=("#ebebf5", "#21213a"),
            corner_radius=18,
            width=40, height=40,
        )
        self._icon_lbl.pack(side="left")

        title_col = ctk.CTkFrame(hdr, fg_color="transparent")
        title_col.pack(side="left", padx=(12, 0))

        ctk.CTkLabel(
            title_col, text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        self._subtitle = ctk.CTkLabel(
            title_col, text="Waiting for scan…",
            font=ctk.CTkFont(size=10),
            text_color=("#aaaaaa", "#666677"),
            anchor="w",
        )
        self._subtitle.pack(anchor="w")

        self._badge = ctk.CTkLabel(
            hdr, text="PENDING",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=("#e8e8f0", "#21213a"),
            corner_radius=8,
            padx=10, pady=4,
            text_color=("#888899", "#666677"),
        )
        self._badge.pack(side="right")

        # separator
        ctk.CTkFrame(body, height=1, fg_color=("#ebebf5", "#21213a")).pack(
            fill="x", pady=(12, 10)
        )

        # content boxes
        self._metrics_box = ctk.CTkFrame(body, fg_color="transparent")
        self._metrics_box.pack(fill="x")

        self._issues_box = ctk.CTkFrame(body, fg_color="transparent")
        self._issues_box.pack(fill="x", pady=(8, 2))

        self._fixes_box = ctk.CTkFrame(body, fg_color="transparent")
        self._fixes_box.pack(fill="x")

        ctk.CTkLabel(
            self._metrics_box, text="Waiting for scan…",
            font=ctk.CTkFont(size=11), text_color=("#bbbbbb", "#555566"),
        ).pack(anchor="w", pady=4)

    # ── public ──────────────────────────────────────────────────────
    def update_result(self, result: CheckResult) -> None:
        fg   = STATUS_FG[result.status]
        bg   = STATUS_BG[result.status]
        icon = STATUS_ICON[result.status]

        self._stripe.configure(fg_color=fg)
        self._icon_lbl.configure(text_color=fg)
        self._badge.configure(text=result.status, fg_color=bg, text_color=fg)

        n = len(result.issues)
        self._subtitle.configure(
            text="All checks passed" if n == 0 else f"{n} issue{'s' if n > 1 else ''} found"
        )

        self._clear(self._metrics_box)
        self._clear(self._issues_box)
        self._clear(self._fixes_box)

        # ── metrics ─────────────────────────────────────────────────
        for key, value in result.metrics.items():
            pct = _extract_pct(str(value))

            row = ctk.CTkFrame(self._metrics_box, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row, text=key,
                font=ctk.CTkFont(size=11),
                text_color=("#777788", "#888899"),
                anchor="w", width=155,
            ).pack(side="left")

            right = ctk.CTkFrame(row, fg_color="transparent")
            right.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                right, text=str(value),
                font=ctk.CTkFont(size=11, weight="bold"),
                anchor="w",
            ).pack(anchor="w")

            if pct is not None:
                bar = ctk.CTkProgressBar(right, height=5, corner_radius=3)
                bar.pack(fill="x", pady=(2, 0))
                bar.set(pct)
                bar.configure(progress_color=_pct_bar_color(pct))

        # ── issues ──────────────────────────────────────────────────
        for issue in result.issues:
            bubble = ctk.CTkFrame(self._issues_box, fg_color=bg, corner_radius=8)
            bubble.pack(fill="x", pady=2)
            ctk.CTkLabel(
                bubble,
                text=f"  {icon}  {issue}",
                font=ctk.CTkFont(size=11),
                text_color=fg,
                anchor="w",
                wraplength=720,
                justify="left",
            ).pack(fill="x", padx=10, pady=6)

        # ── fixes ───────────────────────────────────────────────────
        if result.fixes:
            ctk.CTkLabel(
                self._fixes_box,
                text="  Suggested Fixes",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("#3d8fd4", "#4fc3f7"),
                anchor="w",
            ).pack(fill="x", pady=(8, 2))

            for fix in result.fixes:
                fb = ctk.CTkFrame(self._fixes_box, fg_color=("#e4f2fc", "#0b1f33"), corner_radius=8)
                fb.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    fb,
                    text=f"  →  {fix}",
                    font=ctk.CTkFont(size=11),
                    text_color=("#1a5f99", "#4fc3f7"),
                    anchor="w",
                    wraplength=720,
                    justify="left",
                ).pack(fill="x", padx=10, pady=6)

    def reset(self) -> None:
        self._stripe.configure(fg_color="#444455")
        self._icon_lbl.configure(text_color="#666688")
        self._badge.configure(
            text="SCANNING…",
            fg_color=("#e8e8f0", "#21213a"),
            text_color=("#888899", "#666677"),
        )
        self._subtitle.configure(text="Scanning…")
        self._clear(self._metrics_box)
        self._clear(self._issues_box)
        self._clear(self._fixes_box)
        ctk.CTkLabel(
            self._metrics_box, text="Running check…",
            font=ctk.CTkFont(size=11), text_color=("#bbbbbb", "#555566"),
        ).pack(anchor="w", pady=4)

    @staticmethod
    def _clear(frame: ctk.CTkFrame) -> None:
        for w in frame.winfo_children():
            w.destroy()


# ───────────────────────── main window ─────────────────────────────
class App(ctk.CTk):
    CHECK_ORDER = ["CPU", "Memory", "Disk", "Network", "Processes", "System Health"]

    def __init__(self):
        super().__init__()
        self.title("System Diagnostic Tool")
        self.geometry("920x880")
        self.minsize(700, 600)

        self._diag     = SystemDiagnostics()
        self._results: dict[str, CheckResult] = {}
        self._queue:   queue.Queue = queue.Queue()
        self._scanning = False

        self._build_ui()
        self._poll()

    # ── layout ───────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # ── top bar ─────────────────────────────────────────────────
        topbar = ctk.CTkFrame(self, height=56, fg_color=("#0f0f1a", "#090912"), corner_radius=0)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        ti = ctk.CTkFrame(topbar, fg_color="transparent")
        ti.pack(fill="both", expand=True, padx=20, pady=12)

        ctk.CTkLabel(
            ti, text="⚙  System Diagnostic Tool",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#4fc3f7",
        ).pack(side="left")

        ctk.CTkLabel(
            ti,
            text=f"  {platform.node()}  ·  {platform.system()} {platform.release()}",
            font=ctk.CTkFont(size=12),
            text_color=("#999999", "#666677"),
        ).pack(side="left", padx=16)

        self._scan_time = ctk.CTkLabel(
            ti, text="Last scan: never",
            font=ctk.CTkFont(size=11),
            text_color=("#777788", "#555566"),
        )
        self._scan_time.pack(side="right")

        # ── bottom bar ───────────────────────────────────────────────
        botbar = ctk.CTkFrame(self, height=48, fg_color=("#0f0f1a", "#090912"), corner_radius=0)
        botbar.pack(fill="x", side="bottom")
        botbar.pack_propagate(False)

        bi = ctk.CTkFrame(botbar, fg_color="transparent")
        bi.pack(fill="both", expand=True, padx=20, pady=10)

        self._health_lbl = ctk.CTkLabel(
            bi, text="System Health: — / 100",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#4fc3f7",
        )
        self._health_lbl.pack(side="left")

        self._status_lbl = ctk.CTkLabel(
            bi, text="Run a diagnostic to begin",
            font=ctk.CTkFont(size=11),
            text_color=("#777788", "#555566"),
        )
        self._status_lbl.pack(side="right")

        # ── content ──────────────────────────────────────────────────
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=12)

        # control row
        ctrl = ctk.CTkFrame(content, fg_color="transparent")
        ctrl.pack(fill="x", pady=(0, 10))

        self._run_btn = ctk.CTkButton(
            ctrl, text="▶  Run Diagnostic",
            command=self._start_scan,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, width=215, corner_radius=10,
        )
        self._run_btn.pack(side="left")

        self._export_btn = ctk.CTkButton(
            ctrl, text="⬇  Export Report",
            command=self._export,
            font=ctk.CTkFont(size=13),
            height=44, width=180, corner_radius=10,
            fg_color=("#5c6bc0", "#3949ab"),
            hover_color=("#3949ab", "#283593"),
            state="disabled",
        )
        self._export_btn.pack(side="left", padx=10)

        self._theme_var = ctk.StringVar(value="Dark")
        ctk.CTkSwitch(
            ctrl, text="Light mode",
            variable=self._theme_var, onvalue="Light", offvalue="Dark",
            command=lambda: ctk.set_appearance_mode(self._theme_var.get()),
        ).pack(side="right")

        # progress
        self._prog_lbl = ctk.CTkLabel(
            content, text="Ready",
            font=ctk.CTkFont(size=11),
            text_color=("#888899", "#555566"),
            anchor="w",
        )
        self._prog_lbl.pack(fill="x")

        self._prog_bar = ctk.CTkProgressBar(content, height=7, corner_radius=4)
        self._prog_bar.pack(fill="x", pady=(2, 10))
        self._prog_bar.set(0)

        # ── overview strip ───────────────────────────────────────────
        ov_frame = ctk.CTkFrame(
            content, fg_color=("#eaeaf4", "#12121f"), corner_radius=10, height=46
        )
        ov_frame.pack(fill="x", pady=(0, 10))
        ov_frame.pack_propagate(False)

        ov_inner = ctk.CTkFrame(ov_frame, fg_color="transparent")
        ov_inner.pack(fill="both", expand=True, padx=10, pady=7)

        self._pills: dict[str, ctk.CTkLabel] = {}
        for name in self.CHECK_ORDER:
            pill = ctk.CTkLabel(
                ov_inner,
                text=f"{CARD_ICONS[name]}  {name}",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#e0e0ee", "#21213a"),
                corner_radius=8,
                padx=10, pady=3,
                text_color=("#999999", "#555566"),
            )
            pill.pack(side="left", padx=3)
            self._pills[name] = pill

        # ── single-column scrollable cards ───────────────────────────
        scroll = ctk.CTkScrollableFrame(
            content, fg_color=("gray90", "#111120"), corner_radius=12
        )
        scroll.pack(fill="both", expand=True)

        self._cards: dict[str, DiagnosticCard] = {}
        for name in self.CHECK_ORDER:
            card = DiagnosticCard(scroll, name, icon=CARD_ICONS[name])
            card.pack(fill="x", padx=10, pady=6)
            self._cards[name] = card

    # ── scan lifecycle ────────────────────────────────────────────────
    def _start_scan(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._results.clear()
        self._run_btn.configure(state="disabled", text="⏳  Scanning…")
        self._export_btn.configure(state="disabled")
        self._prog_bar.set(0)
        self._prog_lbl.configure(text="Starting diagnostic…")
        self._health_lbl.configure(text="System Health: — / 100", text_color="#4fc3f7")
        self._status_lbl.configure(text="Scan in progress…")

        for pill in self._pills.values():
            pill.configure(
                fg_color=("#e0e0ee", "#21213a"),
                text_color=("#999999", "#555566"),
            )
        for card in self._cards.values():
            card.reset()

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        checks = [
            ("CPU",           self._diag.check_cpu),
            ("Memory",        self._diag.check_memory),
            ("Disk",          self._diag.check_disk),
            ("Network",       self._diag.check_network),
            ("Processes",     self._diag.check_processes),
            ("System Health", self._diag.check_system_health),
        ]
        for i, (name, fn) in enumerate(checks):
            self._queue.put(("progress", (i / len(checks), f"Checking {name}…")))
            try:
                result = fn()
            except Exception as exc:
                result = CheckResult(name, "UNKNOWN", issues=[f"Check failed: {exc}"])
            self._queue.put(("result", (name, result)))

        self._queue.put(("progress", (1.0, "Diagnostic complete")))
        self._queue.put(("done", None))

    def _poll(self) -> None:
        try:
            while True:
                kind, data = self._queue.get_nowait()
                if kind == "progress":
                    pct, msg = data
                    self._prog_bar.set(pct)
                    self._prog_lbl.configure(text=msg)
                elif kind == "result":
                    name, result = data
                    self._results[name] = result
                    self._cards[name].update_result(result)
                    pill = self._pills.get(name)
                    if pill:
                        fg = STATUS_FG[result.status]
                        bg = STATUS_BG[result.status]
                        pill.configure(
                            fg_color=bg,
                            text_color=fg,
                            text=f"{STATUS_ICON[result.status]}  {name}",
                        )
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _finish(self) -> None:
        self._scanning = False
        self._run_btn.configure(state="normal", text="▶  Run Diagnostic")
        self._export_btn.configure(state="normal")
        self._scan_time.configure(
            text=f"Last scan: {datetime.now().strftime('%H:%M:%S')}"
        )

        score = health_score(self._results)
        color = (
            STATUS_FG["OK"]       if score >= 80 else
            STATUS_FG["WARNING"]  if score >= 60 else
            STATUS_FG["CRITICAL"]
        )
        self._health_lbl.configure(text=f"System Health: {score} / 100", text_color=color)

        total_issues = sum(len(r.issues) for r in self._results.values())
        self._status_lbl.configure(
            text=f"Scan complete — {total_issues} issue(s) found across {len(self._results)} categories"
        )

    # ── export ────────────────────────────────────────────────────────
    def _export(self) -> None:
        if not self._results:
            return

        desktop = Path.home() / "Desktop"
        if not desktop.is_dir():
            desktop = Path.home()

        stamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = desktop / f"system_diagnostic_{stamp}.txt"

        score = health_score(self._results)
        lines = [
            "=" * 64,
            "  SYSTEM DIAGNOSTIC REPORT",
            "=" * 64,
            f"  Machine   : {platform.node()}",
            f"  OS        : {platform.system()} {platform.release()} {platform.version()}",
            f"  Arch      : {platform.machine()}",
            f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Health    : {score} / 100",
            "",
        ]

        for name in self.CHECK_ORDER:
            r = self._results.get(name)
            if not r:
                continue
            lines += [
                "-" * 64,
                f"  [{r.status:8}]  {name.upper()}",
                "-" * 64,
            ]
            for k, v in r.metrics.items():
                lines.append(f"    {k:<24}: {v}")
            if r.issues:
                lines.append("    Issues:")
                for issue in r.issues:
                    lines.append(f"      !  {issue}")
            if r.fixes:
                lines.append("    Suggested Fixes:")
                for fix in r.fixes:
                    lines.append(f"      ->  {fix}")
            lines.append("")

        lines += ["=" * 64, "  END OF REPORT", "=" * 64]

        out_path.write_text("\n".join(lines), encoding="utf-8")
        self._status_lbl.configure(text=f"Report saved → {out_path}")


# ───────────────────────────── entry ───────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
