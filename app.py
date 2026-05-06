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
import os
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
STATUS_BG: dict[str, tuple[str, str]] = {
    "OK":       ("#d4edda", "#12301e"),
    "WARNING":  ("#fff3cd", "#2e2300"),
    "CRITICAL": ("#f8d7da", "#300a0a"),
    "UNKNOWN":  ("#e2e3e5", "#1e1e2e"),
}
STATUS_ICON: dict[str, str] = {
    "OK":       "✓",
    "WARNING":  "⚠",
    "CRITICAL": "✗",
    "UNKNOWN":  "?",
}


# ───────────────────────── data model ──────────────────────────────
@dataclass
class CheckResult:
    name: str
    status: str = "UNKNOWN"          # OK | WARNING | CRITICAL | UNKNOWN
    metrics: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    fixes: list = field(default_factory=list)   # actionable suggestions


def _fmt_bytes(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


# ─────────────────────── diagnostic engine ─────────────────────────
class SystemDiagnostics:
    """All diagnostic checks live here; each returns a CheckResult."""

    # ── CPU ──────────────────────────────────────────────────────────
    def check_cpu(self) -> CheckResult:
        r = CheckResult("CPU", "OK")

        # Model
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

        # Temperature
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
                label = f"{part.device}"
                r.metrics[label] = (
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
            r.metrics[f"{iface} IP"] = ", ".join(ipv4)

            io = io_all.get(iface)
            if io:
                r.metrics[f"{iface} Sent"] = _fmt_bytes(io.bytes_sent)
                r.metrics[f"{iface} Recv"] = _fmt_bytes(io.bytes_recv)
                if io.errin or io.errout:
                    r.issues.append(
                        f"{iface}: {io.errin} inbound / {io.errout} outbound errors"
                    )
                    if r.status == "OK":
                        r.status = "WARNING"
                    r.fixes.append(
                        f"Network errors on {iface}: update your network adapter driver "
                        "via Device Manager → Network Adapters → right-click → Update driver. "
                        "Also try a different Ethernet cable, or switch WiFi bands (2.4 GHz ↔ 5 GHz)."
                    )
                if io.dropin or io.dropout:
                    r.issues.append(
                        f"{iface}: {io.dropin} inbound / {io.dropout} outbound drops"
                    )
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

        time.sleep(0.3)   # let cpu_percent settle for first sample

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
            f"{p['name']} ({p.get('cpu_percent', 0):.1f}%)" for p in by_cpu if p.get("cpu_percent")
        )
        if cpu_str:
            r.metrics["Top CPU"] = cpu_str

        mem_str = ", ".join(
            f"{p['name']} ({p.get('memory_percent', 0):.1f}%)" for p in by_mem if p.get("memory_percent")
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

        # Uptime
        boot = psutil.boot_time()
        uptime = timedelta(seconds=int(time.time() - boot))
        d = uptime.days
        h, rem = divmod(uptime.seconds, 3600)
        m = rem // 60
        r.metrics["Uptime"]    = f"{d}d {h}h {m}m"
        r.metrics["Boot Time"] = datetime.fromtimestamp(boot).strftime("%Y-%m-%d %H:%M:%S")

        # Failed services — Linux (systemd)
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

        # Failed services — macOS (launchctl)
        elif system == "Darwin":
            try:
                out = subprocess.run(
                    ["launchctl", "list"], capture_output=True, text=True, timeout=5
                )
                # Non-zero exit codes in first column indicate failed jobs
                bad = [
                    l for l in out.stdout.splitlines()
                    if l and not l.startswith("PID") and l.split()[0] not in ("-", "0")
                ]
                r.metrics["Launchd Issues"] = str(len(bad)) if bad else "None"
            except Exception:
                r.metrics["Launchd Issues"] = "Unknown"

        # Pending updates — Linux
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
                        out = subprocess.run(
                            cmd, capture_output=True, text=True, timeout=20
                        )
                        pkgs = parser(out.stdout)
                        r.metrics["Pending Updates"] = f"{len(pkgs)} package(s)" if pkgs else "Up to date"
                        if len(pkgs) > 10:
                            r.issues.append(f"{len(pkgs)} pending OS updates")
                            if r.status == "OK":
                                r.status = "WARNING"
                            r.fixes.append(
                                f"Install {len(pkgs)} pending updates by running: "
                                "sudo apt upgrade   (or  sudo dnf upgrade  /  sudo yum upgrade  "
                                "depending on your distro)."
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
                "Keep Windows updated to get security patches and bug fixes."
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
    """Single category result card."""

    def __init__(self, parent, title: str, **kw):
        super().__init__(parent, corner_radius=12, fg_color=("#f5f5f5", "#1e1e2e"), **kw)

        # ── header ──────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 4))

        self._dot = ctk.CTkLabel(
            hdr, text="●", font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#95a5a6", width=26,
        )
        self._dot.pack(side="left")

        ctk.CTkLabel(
            hdr, text=title, font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left", padx=(4, 0))

        self._badge = ctk.CTkLabel(
            hdr, text="PENDING",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=("#e0e0e0", "#2a2a3e"),
            corner_radius=6,
            padx=8, pady=2,
            text_color=("#777777", "#aaaaaa"),
        )
        self._badge.pack(side="right")

        # separator
        ctk.CTkFrame(self, height=1, fg_color=("#dddddd", "#2a2a3e")).pack(
            fill="x", padx=14, pady=(2, 6)
        )

        # ── metrics, issues, fixes containers ───────────────────────
        self._metrics_box = ctk.CTkFrame(self, fg_color="transparent")
        self._metrics_box.pack(fill="x", padx=14)

        self._issues_box = ctk.CTkFrame(self, fg_color="transparent")
        self._issues_box.pack(fill="x", padx=14, pady=(4, 2))

        self._fixes_box = ctk.CTkFrame(self, fg_color="transparent")
        self._fixes_box.pack(fill="x", padx=14, pady=(0, 12))

        # spacer at bottom so empty cards don't collapse completely
        self._placeholder = ctk.CTkLabel(
            self._metrics_box, text="Waiting for scan…",
            font=ctk.CTkFont(size=11), text_color=("#aaaaaa", "#555555"),
        )
        self._placeholder.pack(anchor="w", pady=4)

    # ── public API ───────────────────────────────────────────────────
    def update_result(self, result: CheckResult) -> None:
        fg   = STATUS_FG[result.status]
        bg   = STATUS_BG[result.status]
        icon = STATUS_ICON[result.status]

        self._dot.configure(text_color=fg)
        self._badge.configure(text=result.status, fg_color=bg, text_color=fg)

        self._clear(self._metrics_box)
        self._clear(self._issues_box)
        self._clear(self._fixes_box)

        # metrics
        for key, value in result.metrics.items():
            row = ctk.CTkFrame(self._metrics_box, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row, text=f"{key}:", font=ctk.CTkFont(size=11),
                text_color=("#666666", "#888888"),
                anchor="w", width=160,
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=str(value), font=ctk.CTkFont(size=11, weight="bold"),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

        # issues
        for issue in result.issues:
            bubble = ctk.CTkFrame(self._issues_box, fg_color=bg, corner_radius=6)
            bubble.pack(fill="x", pady=2)
            ctk.CTkLabel(
                bubble,
                text=f"  {icon}  {issue}",
                font=ctk.CTkFont(size=11),
                text_color=fg,
                anchor="w",
                wraplength=360,
                justify="left",
            ).pack(fill="x", padx=6, pady=4)

        # fixes
        if result.fixes:
            ctk.CTkLabel(
                self._fixes_box,
                text="  Suggested Fixes",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("#4a90d9", "#4fc3f7"),
                anchor="w",
            ).pack(fill="x", pady=(4, 2))
            for fix in result.fixes:
                fix_bubble = ctk.CTkFrame(
                    self._fixes_box,
                    fg_color=("#e8f4fd", "#0d2137"),
                    corner_radius=6,
                )
                fix_bubble.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    fix_bubble,
                    text=f"  →  {fix}",
                    font=ctk.CTkFont(size=11),
                    text_color=("#1a5f99", "#4fc3f7"),
                    anchor="w",
                    wraplength=360,
                    justify="left",
                ).pack(fill="x", padx=6, pady=5)

    def reset(self) -> None:
        self._dot.configure(text_color="#95a5a6")
        self._badge.configure(
            text="SCANNING…",
            fg_color=("#e0e0e0", "#2a2a3e"),
            text_color=("#777777", "#aaaaaa"),
        )
        self._clear(self._metrics_box)
        self._clear(self._issues_box)
        self._clear(self._fixes_box)
        self._placeholder = ctk.CTkLabel(
            self._metrics_box, text="Running check…",
            font=ctk.CTkFont(size=11), text_color=("#aaaaaa", "#555555"),
        )
        self._placeholder.pack(anchor="w", pady=4)

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
        self.geometry("980x820")
        self.minsize(780, 600)

        self._diag     = SystemDiagnostics()
        self._results: dict[str, CheckResult] = {}
        self._queue:   queue.Queue = queue.Queue()
        self._scanning = False

        self._build_ui()
        self._poll()

    # ── layout ───────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # top bar
        topbar = ctk.CTkFrame(self, height=52, fg_color=("#1a1a2e", "#0d0d1a"), corner_radius=0)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        inner = ctk.CTkFrame(topbar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=10)

        ctk.CTkLabel(
            inner, text="⚙  System Diagnostic Tool",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#4fc3f7",
        ).pack(side="left")

        ctk.CTkLabel(
            inner,
            text=f"  {platform.node()}  ·  {platform.system()} {platform.release()}",
            font=ctk.CTkFont(size=12),
            text_color=("#aaaaaa", "#777777"),
        ).pack(side="left", padx=16)

        self._scan_time = ctk.CTkLabel(
            inner, text="Last scan: never",
            font=ctk.CTkFont(size=11),
            text_color=("#888888", "#555555"),
        )
        self._scan_time.pack(side="right")

        # bottom health bar
        botbar = ctk.CTkFrame(self, height=46, fg_color=("#1a1a2e", "#0d0d1a"), corner_radius=0)
        botbar.pack(fill="x", side="bottom")
        botbar.pack_propagate(False)

        bot_inner = ctk.CTkFrame(botbar, fg_color="transparent")
        bot_inner.pack(fill="both", expand=True, padx=18, pady=10)

        self._health_lbl = ctk.CTkLabel(
            bot_inner, text="System Health: — / 100",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#4fc3f7",
        )
        self._health_lbl.pack(side="left")

        self._status_lbl = ctk.CTkLabel(
            bot_inner, text="Run a diagnostic to begin",
            font=ctk.CTkFont(size=11),
            text_color=("#888888", "#555555"),
        )
        self._status_lbl.pack(side="right")

        # main content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=10)

        # control row
        ctrl = ctk.CTkFrame(content, fg_color="transparent")
        ctrl.pack(fill="x", pady=(0, 8))

        self._run_btn = ctk.CTkButton(
            ctrl, text="▶  Run Diagnostic",
            command=self._start_scan,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42, width=200, corner_radius=10,
        )
        self._run_btn.pack(side="left")

        self._export_btn = ctk.CTkButton(
            ctrl, text="⬇  Export Report",
            command=self._export,
            font=ctk.CTkFont(size=13),
            height=42, width=170, corner_radius=10,
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
            text_color=("#888888", "#555555"),
            anchor="w",
        )
        self._prog_lbl.pack(fill="x")

        self._prog_bar = ctk.CTkProgressBar(content, height=6)
        self._prog_bar.pack(fill="x", pady=(2, 10))
        self._prog_bar.set(0)

        # scrollable card grid
        scroll = ctk.CTkScrollableFrame(content, fg_color=("gray91", "gray13"), corner_radius=10)
        scroll.pack(fill="both", expand=True)

        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=4, pady=4)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self._cards: dict[str, DiagnosticCard] = {}
        for idx, name in enumerate(self.CHECK_ORDER):
            row, col = divmod(idx, 2)
            card = DiagnosticCard(grid, name)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
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
        total = len(checks)

        for i, (name, fn) in enumerate(checks):
            self._queue.put(("progress", (i / total, f"Checking {name}…")))
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
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _finish(self) -> None:
        self._scanning = False
        self._run_btn.configure(state="normal", text="▶  Run Diagnostic")
        self._export_btn.configure(state="normal")

        now = datetime.now()
        self._scan_time.configure(text=f"Last scan: {now.strftime('%H:%M:%S')}")

        score = health_score(self._results)
        color = (
            STATUS_FG["OK"]       if score >= 80 else
            STATUS_FG["WARNING"]  if score >= 60 else
            STATUS_FG["CRITICAL"]
        )
        self._health_lbl.configure(text=f"System Health: {score} / 100", text_color=color)

        total_issues = sum(len(r.issues) for r in self._results.values())
        self._status_lbl.configure(
            text=f"Scan complete — {total_issues} issue(s) found across "
                 f"{len(self._results)} categories"
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
            "=" * 62,
            "  SYSTEM DIAGNOSTIC REPORT",
            "=" * 62,
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
                "-" * 62,
                f"  [{r.status:8}]  {name.upper()}",
                "-" * 62,
            ]
            for k, v in r.metrics.items():
                lines.append(f"    {k:<22}: {v}")
            if r.issues:
                lines.append("    Issues:")
                for issue in r.issues:
                    lines.append(f"      !  {issue}")
            if r.fixes:
                lines.append("    Suggested Fixes:")
                for fix in r.fixes:
                    lines.append(f"      →  {fix}")
            lines.append("")

        lines += ["=" * 62, "  END OF REPORT", "=" * 62]

        out_path.write_text("\n".join(lines), encoding="utf-8")
        self._status_lbl.configure(text=f"Report saved → {out_path}")


# ───────────────────────────── entry ───────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
