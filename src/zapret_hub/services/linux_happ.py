from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Callable, Iterable


@dataclass(frozen=True, slots=True)
class LinuxHappResult:
    status: str
    message: str = ""
    pid: int | None = None
    command: tuple[str, ...] = ()
    returncode: int | None = None


class LinuxHappService:
    """Control the official Happ Linux client through its public deeplinks.

    Happ owns its privileged daemon, tunnel, routes, and configuration. Zapret
    Hub only asks the already-installed GUI to connect/disconnect and observes
    the official Xray/sing-box child processes. The daemon is never stopped.
    """

    _CORE_EXECUTABLES = (
        Path("/opt/happ/bin/core/xray"),
        Path("/opt/happ/bin/tun/sing-box"),
        Path("/opt/happ/bin/tun2/tun2proxy-bin"),
    )

    def __init__(
        self,
        *,
        executable_candidates: Iterable[Path] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        popen: Callable[..., subprocess.Popen[object]] = subprocess.Popen,
        which: Callable[[str], str | None] = shutil.which,
        geteuid: Callable[[], int] | None = getattr(os, "geteuid", None),
        connected_pid: Callable[[], int | None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        platform_name: str = sys.platform,
    ) -> None:
        self._executable_candidates = tuple(
            executable_candidates or (Path("/usr/bin/happ"), Path("/opt/happ/bin/Happ"))
        )
        self._runner = runner
        self._popen = popen
        self._which = which
        self._geteuid = geteuid
        self._connected_pid_override = connected_pid
        self._sleep = sleep
        self._platform_name = platform_name

    @property
    def supported(self) -> bool:
        return self._platform_name.startswith("linux")

    @property
    def available(self) -> bool:
        return self.find_executable() is not None

    def find_executable(self) -> Path | None:
        for candidate in self._executable_candidates:
            path = Path(candidate).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return path.resolve()
        located = self._which("happ")
        return Path(located).resolve() if located else None

    def connected_pid(self) -> int | None:
        if self._connected_pid_override is not None:
            return self._connected_pid_override()
        expected = {str(path) for path in self._CORE_EXECUTABLES}
        proc_root = Path("/proc")
        try:
            entries = proc_root.iterdir()
        except OSError:
            return None
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                executable = str((entry / "exe").resolve(strict=True))
            except OSError:
                continue
            if executable in expected:
                return int(entry.name)
        return None

    def status(self) -> LinuxHappResult:
        if not self.supported:
            return LinuxHappResult("unsupported", "Happ integration is available only on Linux")
        if not self.available:
            return LinuxHappResult("unavailable", "Happ is not installed")
        pid = self.connected_pid()
        if pid is not None:
            return LinuxHappResult("running", pid=pid)
        return LinuxHappResult("stopped", "Happ is installed but disconnected")

    def open(self) -> LinuxHappResult:
        return self._launch("happ://open", wait_for="none")

    def start(self) -> LinuxHappResult:
        current = self.status()
        if current.status == "running":
            return current
        daemon = self._ensure_daemon()
        if daemon.status == "error":
            return daemon
        return self._launch("happ://connect", wait_for="running")

    def stop(self) -> LinuxHappResult:
        current = self.status()
        if current.status in {"stopped", "unavailable", "unsupported"}:
            return current
        return self._launch("happ://disconnect", wait_for="stopped")

    def version(self) -> str:
        dpkg_query = self._which("dpkg-query")
        if not dpkg_query:
            return ""
        result = self._run(
            [dpkg_query, "-W", "-f=${Version}", "happ"],
            timeout=5,
        )
        return (result.stdout or "").strip() if result.returncode == 0 else ""

    def diagnose(self) -> dict[str, object]:
        state = self.status()
        daemon_state = self._daemon_state()
        return {
            "supported": self.supported,
            "available": self.available,
            "executable": str(self.find_executable() or ""),
            "version": self.version(),
            "daemon": daemon_state,
            "status": state.status,
            "pid": state.pid,
            "ready": bool(self.supported and self.available and daemon_state == "active"),
        }

    def _launch(self, deeplink: str, *, wait_for: str) -> LinuxHappResult:
        executable = self.find_executable()
        if executable is None:
            return LinuxHappResult("error", "Happ is not installed")
        command = [str(executable), deeplink]
        try:
            self._popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        except OSError as error:
            return LinuxHappResult("error", str(error), command=tuple(command))

        if wait_for == "none":
            return LinuxHappResult("opened", command=tuple(command), returncode=0)
        for _ in range(30):
            pid = self.connected_pid()
            if wait_for == "running" and pid is not None:
                return LinuxHappResult("running", pid=pid, command=tuple(command), returncode=0)
            if wait_for == "stopped" and pid is None:
                return LinuxHappResult("stopped", command=tuple(command), returncode=0)
            self._sleep(0.5)
        if wait_for == "running":
            return LinuxHappResult(
                "error",
                "Happ did not establish a tunnel. Open Happ and select or import a server.",
                command=tuple(command),
            )
        return LinuxHappResult(
            "error",
            "Happ is still connected after the disconnect request.",
            pid=self.connected_pid(),
            command=tuple(command),
        )

    def _daemon_state(self) -> str:
        systemctl = self._which("systemctl")
        if not systemctl:
            return "unknown"
        result = self._run([systemctl, "is-active", "happd.service"], timeout=5)
        state = (result.stdout or "").strip().lower()
        return state or ("active" if result.returncode == 0 else "inactive")

    def _ensure_daemon(self) -> LinuxHappResult:
        if self._daemon_state() == "active":
            return LinuxHappResult("ready")
        systemctl = self._which("systemctl")
        if not systemctl:
            return LinuxHappResult("error", "systemctl was not found")
        command = [systemctl, "start", "happd.service"]
        if not self._is_root():
            pkexec = self._which("pkexec")
            if not pkexec:
                return LinuxHappResult("error", "pkexec was not found", command=tuple(command))
            command.insert(0, pkexec)
        result = self._run(command, timeout=30)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Failed to start happd.service").strip()
            return LinuxHappResult("error", message, command=tuple(command), returncode=result.returncode)
        return LinuxHappResult("ready", command=tuple(command), returncode=0)

    def _run(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return subprocess.CompletedProcess(command, 1, "", str(error))

    def _is_root(self) -> bool:
        return bool(self._geteuid is not None and self._geteuid() == 0)
