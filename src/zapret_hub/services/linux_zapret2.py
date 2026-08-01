from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Iterable


_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


@dataclass(frozen=True, slots=True)
class LinuxServiceResult:
    status: str
    message: str = ""
    service: str = "zapret2.service"
    command: tuple[str, ...] = ()
    returncode: int | None = None


class LinuxZapret2Service:
    """Discover and control an upstream zapret2 installation on Linux.

    Zapret Hub deliberately delegates firewall setup to zapret2's own service.
    Starting nfqws2 without the matching nftables/iptables rules would look
    successful in the UI while doing nothing useful (or could disrupt traffic).
    """

    def __init__(
        self,
        *,
        service_name: str | None = None,
        root_candidates: Iterable[Path] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        geteuid: Callable[[], int] | None = getattr(os, "geteuid", None),
        platform_name: str = sys.platform,
    ) -> None:
        configured_service = str(
            service_name or os.environ.get("ZAPRET_HUB_ZAPRET2_SERVICE", "zapret2.service")
        ).strip()
        if not configured_service or not _SERVICE_RE.fullmatch(configured_service):
            raise ValueError("Invalid zapret2 systemd service name")
        self.service_name = configured_service
        self._runner = runner
        self._which = which
        self._geteuid = geteuid
        self._platform_name = platform_name
        self._root_candidates = tuple(root_candidates or self._default_roots())

    @property
    def supported(self) -> bool:
        return self._platform_name.startswith("linux")

    def discover_root(self) -> Path | None:
        for candidate in self._root_candidates:
            path = Path(candidate).expanduser()
            if path.is_dir():
                return path.resolve()
        return None

    def find_nfqws2(self, root: Path | None = None) -> Path | None:
        base = root or self.discover_root()
        if base is None:
            return None
        machine = platform.machine().lower()
        architecture = {
            "amd64": "x86_64",
            "x86_64": "x86_64",
            "i386": "x86",
            "i686": "x86",
            "aarch64": "arm64",
            "arm64": "arm64",
            "armv7l": "arm",
        }.get(machine, machine)
        candidates = (
            base / "binaries" / "my" / "nfqws2",
            base / "binaries" / f"linux-{architecture}" / "nfqws2",
            base / "nfq2" / "nfqws2",
            base / "nfqws2",
        )
        return next((path.resolve() for path in candidates if path.is_file()), None)

    def status(self) -> LinuxServiceResult:
        if not self.supported:
            return LinuxServiceResult("unsupported", "Linux backend is only available on Linux", self.service_name)
        systemctl = self._which("systemctl")
        if systemctl:
            result = self._run([systemctl, "is-active", self.service_name], timeout=8)
            active_state = (result.stdout or "").strip().lower()
            if result.returncode == 0 and active_state == "active":
                return LinuxServiceResult("running", service=self.service_name, returncode=0)
            if active_state in {"inactive", "failed", "activating", "deactivating"}:
                mapped = "running" if active_state == "activating" else "stopped"
                return LinuxServiceResult(mapped, active_state, self.service_name, returncode=result.returncode)
        pgrep = self._which("pgrep")
        if pgrep:
            result = self._run([pgrep, "-x", "nfqws2"], timeout=5)
            if result.returncode == 0:
                return LinuxServiceResult("running", "nfqws2 is running outside systemd", self.service_name)
        return LinuxServiceResult("stopped", "zapret2 service is not active", self.service_name)

    def start(self, *, dry_run: bool = False) -> LinuxServiceResult:
        return self._control("start", dry_run=dry_run)

    def stop(self, *, dry_run: bool = False) -> LinuxServiceResult:
        return self._control("stop", dry_run=dry_run)

    def diagnose(self) -> dict[str, Any]:
        root = self.discover_root()
        nfqws2 = self.find_nfqws2(root)
        service_manager = self._which("systemctl")
        firewall = self._which("nft") or self._which("iptables")
        elevation = "root" if self._is_root() else (self._which("pkexec") or "")
        state = self.status()
        result = {
            "platform": self._platform_name,
            "supported": self.supported,
            "service": self.service_name,
            "service_manager": service_manager or "",
            "service_state": state.status,
            "service_message": state.message,
            "zapret2_root": str(root) if root else "",
            "nfqws2": str(nfqws2) if nfqws2 else "",
            "firewall_backend": firewall or "",
            "elevation": elevation,
        }
        result["ready"] = bool(
            result["supported"]
            and result["service_manager"]
            and result["zapret2_root"]
            and result["nfqws2"]
            and result["firewall_backend"]
            and result["elevation"]
        )
        return result

    def _control(self, action: str, *, dry_run: bool) -> LinuxServiceResult:
        if not self.supported:
            return LinuxServiceResult("unsupported", "Linux backend is only available on Linux", self.service_name)
        systemctl = self._which("systemctl")
        if not systemctl:
            return LinuxServiceResult("error", "systemctl was not found", self.service_name)
        command = [systemctl, action, self.service_name]
        if not self._is_root():
            pkexec = self._which("pkexec")
            if not pkexec:
                return LinuxServiceResult(
                    "error",
                    "pkexec was not found; install policykit-1 or run the command as root",
                    self.service_name,
                    tuple(command),
                )
            command.insert(0, pkexec)
        if dry_run:
            return LinuxServiceResult("planned", service=self.service_name, command=tuple(command))
        result = self._run(command, timeout=90)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or f"systemctl {action} failed").strip()
            return LinuxServiceResult("error", message, self.service_name, tuple(command), result.returncode)
        expected = "running" if action == "start" else "stopped"
        observed = self.status()
        if observed.status != expected:
            return LinuxServiceResult(
                "error",
                observed.message or f"Service did not become {expected}",
                self.service_name,
                tuple(command),
                result.returncode,
            )
        return LinuxServiceResult(expected, service=self.service_name, command=tuple(command), returncode=0)

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

    @staticmethod
    def _default_roots() -> tuple[Path, ...]:
        explicit = str(os.environ.get("ZAPRET_HUB_ZAPRET2_ROOT", "")).strip()
        roots = [Path(explicit)] if explicit else []
        roots.extend((Path("/opt/zapret2"), Path("/opt/zapret")))
        return tuple(roots)


class LinuxZapretService(LinuxZapret2Service):
    """Control an existing zapret-discord-youtube-linux systemd install.

    The external project remains responsible for its strategy, lists and
    nftables rules.  Zapret Hub only controls the already-installed unit.
    """

    def __init__(
        self,
        *,
        service_name: str | None = None,
        root_candidates: Iterable[Path] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        geteuid: Callable[[], int] | None = getattr(os, "geteuid", None),
        platform_name: str = sys.platform,
    ) -> None:
        configured_service = str(
            service_name
            or os.environ.get("ZAPRET_HUB_ZAPRET_SERVICE", "zapret_discord_youtube.service")
        ).strip()
        super().__init__(
            service_name=configured_service,
            root_candidates=root_candidates or self._default_roots(),
            runner=runner,
            which=which,
            geteuid=geteuid,
            platform_name=platform_name,
        )

    def discover_root(self) -> Path | None:
        # A preserved foreign directory may be incomplete. Continue to the
        # Hub-managed fallback instead of treating the first directory as a
        # usable classic Zapret installation.
        first_directory: Path | None = None
        for candidate in self._root_candidates:
            path = Path(candidate).expanduser()
            if not path.is_dir():
                continue
            resolved = path.resolve()
            first_directory = first_directory or resolved
            if self.find_nfqws(resolved) is not None:
                return resolved
        return first_directory

    def find_nfqws(self, root: Path | None = None) -> Path | None:
        base = root or self.discover_root()
        if base is None:
            return None
        candidates = (
            base / "nfqws",
            base / "bin" / "nfqws",
            base / "binaries" / "nfqws",
        )
        return next((path.resolve() for path in candidates if path.is_file()), None)

    def status(self) -> LinuxServiceResult:
        if not self.supported:
            return LinuxServiceResult(
                "unsupported", "Linux backend is only available on Linux", self.service_name
            )
        systemctl = self._which("systemctl")
        if systemctl:
            result = self._run([systemctl, "is-active", self.service_name], timeout=8)
            active_state = (result.stdout or "").strip().lower()
            if result.returncode == 0 and active_state == "active":
                return LinuxServiceResult("running", service=self.service_name, returncode=0)
            if active_state in {"inactive", "failed", "activating", "deactivating"}:
                mapped = "running" if active_state == "activating" else "stopped"
                return LinuxServiceResult(
                    mapped, active_state, self.service_name, returncode=result.returncode
                )
        pgrep = self._which("pgrep")
        if pgrep:
            result = self._run([pgrep, "-x", "nfqws"], timeout=5)
            if result.returncode == 0:
                return LinuxServiceResult(
                    "running", "nfqws is running outside systemd", self.service_name
                )
        return LinuxServiceResult(
            "stopped", "zapret service is not active", self.service_name
        )

    def diagnose(self) -> dict[str, Any]:
        root = self.discover_root()
        nfqws = self.find_nfqws(root)
        service_manager = self._which("systemctl")
        firewall = self._which("nft") or self._which("iptables")
        elevation = "root" if self._is_root() else (self._which("pkexec") or "")
        state = self.status()
        result = {
            "platform": self._platform_name,
            "supported": self.supported,
            "service": self.service_name,
            "service_manager": service_manager or "",
            "service_state": state.status,
            "service_message": state.message,
            "zapret_root": str(root) if root else "",
            "nfqws": str(nfqws) if nfqws else "",
            "firewall_backend": firewall or "",
            "elevation": elevation,
        }
        result["ready"] = bool(
            result["supported"]
            and result["service_manager"]
            and result["zapret_root"]
            and result["nfqws"]
            and result["firewall_backend"]
            and result["elevation"]
        )
        return result

    @staticmethod
    def _default_roots() -> tuple[Path, ...]:
        explicit = str(os.environ.get("ZAPRET_HUB_ZAPRET_ROOT", "")).strip()
        roots = [Path(explicit)] if explicit else []
        roots.extend(
            (
                Path.home() / "zapret-discord-youtube-linux",
                Path("/opt/zapret-discord-youtube-linux"),
                Path("/opt/zapret-hub/zapret-discord-youtube-linux"),
                Path("/opt/zapret-discord-youtube"),
            )
        )
        return tuple(roots)


def result_dict(result: LinuxServiceResult) -> dict[str, Any]:
    data = asdict(result)
    data["command"] = list(result.command)
    return data
