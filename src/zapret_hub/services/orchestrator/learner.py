from __future__ import annotations

import ipaddress
from pathlib import Path

from zapret_hub.services.orchestrator.conflicts import ConflictDetector


class HostlistLearner:
    """Auto-hostlist: append failing hosts/IPs to user lists after a fail threshold."""

    FAIL_THRESHOLD = 2

    def __init__(self, configs_dir: Path) -> None:
        self.configs_dir = Path(configs_dir)

    def _append_unique(self, filename: str, lines: list[str]) -> list[str]:
        path = self.configs_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[str] = []
        if path.exists():
            existing = [row.rstrip() for row in path.read_text(encoding="utf-8", errors="ignore").splitlines()]
        seen = {row.strip().lower() for row in existing if row.strip() and not row.lstrip().startswith("#")}
        added: list[str] = []
        for line in lines:
            key = line.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            existing.append(line.strip())
            added.append(line.strip())
        if added:
            path.write_text("\n".join(existing) + ("\n" if existing else ""), encoding="utf-8")
        return added

    def add_domains(self, domains: list[str]) -> list[str]:
        cleaned = [d.strip().lower().rstrip(".") for d in domains if d and d.strip()]
        return self._append_unique("list-general-user.txt", cleaned)

    def exclude_domains(self, domains: list[str]) -> list[str]:
        cleaned = [d.strip().lower().rstrip(".") for d in domains if d and d.strip()]
        return self._append_unique("list-exclude-user.txt", cleaned)

    def add_ips(self, ips: list[str]) -> list[str]:
        cleaned = [item.strip() for item in ips if item and item.strip()]
        return self._append_unique("ipset-all-user.txt", cleaned)

    @staticmethod
    def _domain_match(host: str, entry: str) -> bool:
        host = host.strip().lower().rstrip(".")
        entry = entry.strip().lower().rstrip(".")
        if not host or not entry or entry.startswith("#"):
            return False
        return host == entry or host.endswith("." + entry)

    @staticmethod
    def _ip_match(address: str, entry: str) -> bool:
        try:
            target = ipaddress.ip_address(address)
        except ValueError:
            return False
        try:
            if "/" in entry:
                return target in ipaddress.ip_network(entry, strict=False)
            return target == ipaddress.ip_address(entry)
        except ValueError:
            return False

    def domain_in_merged_lists(self, domain: str, lists_dirs: list[Path]) -> bool:
        host = domain.strip().lower().rstrip(".")
        if not host:
            return False
        names = ("list-general.txt", "list-general-user.txt", "list-google.txt")
        for directory in lists_dirs:
            for name in names:
                path = directory / name
                if not path.exists():
                    continue
                try:
                    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue
                for line in lines:
                    entry = line.strip()
                    if self._domain_match(host, entry):
                        return True
        return False

    def ip_in_merged_lists(self, ip: str, lists_dirs: list[Path]) -> bool:
        address = (ip or "").strip()
        if not address:
            return False
        names = ("ipset-all.txt", "ipset-all-user.txt")
        for directory in lists_dirs:
            for name in names:
                path = directory / name
                if not path.exists():
                    continue
                try:
                    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue
                for line in lines:
                    entry = line.strip()
                    if not entry or entry.startswith("#"):
                        continue
                    if self._ip_match(address, entry):
                        return True
        return False

    def classify(
        self,
        *,
        host: str,
        probe_ok: bool,
        probe_error: str = "",
        lists_dirs: list[Path] | None = None,
    ) -> str:
        if probe_ok:
            return "ok"
        err = (probe_error or "").lower()
        if "getaddrinfo" in err or "name or service not known" in err or "nodename" in err:
            return "dead_host"
        in_lists = self.domain_in_merged_lists(host, lists_dirs or [self.configs_dir])
        if not in_lists:
            return "external_miss"
        return "suspect_overblock"


def learn_host(
    host: str,
    *,
    success: bool = False,
    configs_dir: Path | None = None,
    fail_count: int = 0,
    threshold: int = HostlistLearner.FAIL_THRESHOLD,
) -> list[str]:
    if not host or configs_dir is None or success:
        return []
    if fail_count and fail_count < threshold:
        return []
    learner = HostlistLearner(configs_dir)
    return learner.add_domains([host])


__all__ = [
    "HostlistLearner",
    "ConflictDetector",
    "learn_host",
]
