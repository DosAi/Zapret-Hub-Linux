from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from zapret_hub.services.orchestrator.learner import HostlistLearner
from zapret_hub.services.orchestrator.signals import ProbeResult, SignalCollector, probe_required_ok
from zapret_hub.services.orchestrator.tuner import TunerStep
from zapret_hub.services.service_catalog import SERVICE_PRESET_IDS, SERVICE_PRESETS
from zapret_hub.services.service_rules import SERVICE_RULES


_SETTINGS_KEYS = (
    "selected_zapret_general",
    "zapret_ipset_mode",
    "zapret_game_filter_mode",
    "zapret_gaming_set",
    "selected_service_ids",
    "trusted_general",
    "enabled_mod_ids",
    "enabled_zapret2_mod_ids",
    "zapret2_strategy_id",
)


class CutoverManager:
    """Warm A/B cutover with settings↔runtime always restored together on failure.

    Batches multiple tuner steps into one materialize → stop A → start B → probe.
    """

    def __init__(
        self,
        context: Any,
        *,
        knowledge: Any | None = None,
        signals: SignalCollector | None = None,
    ) -> None:
        self.context = context
        self.knowledge = knowledge
        self.signals = signals or SignalCollector()
        self.last_good: dict[str, Any] | None = None
        self._slot_a: Path | None = None
        self._settle_s = 2.2

    def _log(self, level: str, message: str, **fields: Any) -> None:
        logging = getattr(self.context, "logging", None)
        if logging is None:
            return
        try:
            logging.log(level, message, **fields)
        except Exception:
            pass

    def snapshot(self, *, force_runtime: Path | None = None) -> dict[str, Any]:
        settings = self.context.settings.get()
        payload: dict[str, Any] = {key: getattr(settings, key, None) for key in _SETTINGS_KEYS}
        payload["selected_service_ids"] = list(settings.selected_service_ids or [])
        payload["enabled_mod_ids"] = list(getattr(settings, "enabled_mod_ids", None) or [])
        payload["enabled_zapret2_mod_ids"] = list(getattr(settings, "enabled_zapret2_mod_ids", None) or [])
        live = force_runtime or getattr(self.context.processes, "_current_zapret_runtime", None)
        if live is not None:
            payload["runtime_path"] = str(live)
            self._slot_a = Path(live)
            try:
                self.context.processes.remember_auto_runtime(Path(live))
            except Exception:
                pass
        self.last_good = payload
        if self.knowledge is not None:
            try:
                self.knowledge.save_last_known_good(payload)
            except Exception:
                pass
        return dict(payload)

    def load_last_good(self) -> dict[str, Any]:
        if self.last_good:
            return dict(self.last_good)
        if self.knowledge is not None:
            try:
                stored = self.knowledge.load_last_known_good()
                if stored:
                    self.last_good = dict(stored)
                    return dict(stored)
            except Exception:
                pass
        return {}

    def apply_plan(
        self,
        steps: list[TunerStep] | list[dict[str, Any]] | None,
        *,
        probe_targets: list[dict[str, str]] | None = None,
        required_hosts: list[str] | None = None,
        restart: bool | None = None,
    ) -> dict[str, Any]:
        """Apply ALL steps, then ONE staged cutover + probe. Rollback settings+runtime on fail."""
        if self._runtime_backend() == "zapret2":
            return self._apply_plan_zapret2(
                steps,
                probe_targets=probe_targets,
                required_hosts=required_hosts,
                restart=restart,
            )
        return self._apply_plan_classic(
            steps,
            probe_targets=probe_targets,
            required_hosts=required_hosts,
            restart=restart,
        )

    def _runtime_backend(self) -> str:
        try:
            mode = str(self.context.settings.get().selected_runtime_mode or "zapret")
        except Exception:
            mode = "zapret"
        return "zapret2" if mode == "zapret2" else "zapret"

    def _apply_plan_classic(
        self,
        steps: list[TunerStep] | list[dict[str, Any]] | None,
        *,
        probe_targets: list[dict[str, str]] | None = None,
        required_hosts: list[str] | None = None,
        restart: bool | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_steps(steps)
        normalized = self._coalesce_list_steps(normalized)
        if not normalized:
            return {"ok": True, "applied": [], "skipped": [], "results": [], "restarted": False, "backend": "zapret"}

        was_running = self._zapret_running() if restart is None else bool(restart)
        baseline = self.snapshot()
        live_a = getattr(self.context.processes, "_current_zapret_runtime", None)
        if live_a is not None:
            self._slot_a = Path(live_a)
            try:
                self.context.processes.pin_orchestrator_runtime(self._slot_a)
            except Exception:
                pass

        applied: list[dict[str, Any]] = []
        try:
            for step in normalized:
                self._apply_one_mutation(step, backend="zapret")
                applied.append({"kind": step.kind, "value": step.value, "reason": step.reason})

            if not was_running:
                self._rebuild_snapshot_only()
                self.snapshot()
                return {
                    "ok": True,
                    "applied": applied,
                    "skipped": [],
                    "results": [{"ok": True, "restarted": False}],
                    "restarted": False,
                    "backend": "zapret",
                }

            self._rebuild_snapshot_only()
            slot_b = self._stage_candidate_b()
            self._log("info", "Orchestrator staged candidate B", runtime=str(slot_b), steps=len(applied))

            # Stage B while A still runs, then soft-kill A and start B immediately.
            # (WinDivert cannot run two captures — gap is minimized, not overlap.)
            if hasattr(self.context.processes, "hot_replace_zapret_runtime"):
                started = self.context.processes.hot_replace_zapret_runtime(slot_b)
            else:
                try:
                    self.context.processes.stop_component("zapret")
                except Exception as error:
                    self._log("warning", "Orchestrator stop A failed", error=str(error))
                started = self.context.processes.start_zapret_from_runtime(slot_b)
            restarted = str(getattr(started, "status", "")) == "running"
            if not restarted:
                self._full_rollback(baseline)
                return {
                    "ok": False,
                    "applied": [],
                    "skipped": applied,
                    "results": [],
                    "restarted": False,
                    "rolled_back": True,
                    "error": str(getattr(started, "last_error", "") or "start_b_failed"),
                    "backend": "zapret",
                }

            time.sleep(self._settle_s)
            targets = list(probe_targets or [])
            ok = True
            if targets:
                results = self._probe(targets)
                ok = probe_required_ok(results, required_hosts=required_hosts or [])
            if not ok:
                self._log("info", "Orchestrator candidate B failed probe — full rollback")
                self._full_rollback(baseline)
                return {
                    "ok": False,
                    "applied": [],
                    "skipped": applied,
                    "results": [],
                    "restarted": True,
                    "rolled_back": True,
                    "error": "probe_failed",
                    "backend": "zapret",
                }

            try:
                self.context.processes.pin_orchestrator_runtime(None)
            except Exception:
                pass
            self.snapshot(force_runtime=slot_b)
            try:
                self.context.processes.remember_auto_runtime(slot_b)
                self.context.processes._cleanup_inactive_zapret_runtimes()
            except Exception:
                pass
            return {
                "ok": True,
                "applied": applied,
                "skipped": [],
                "results": [{"ok": True, "restarted": True, "runtime": str(slot_b)}],
                "restarted": True,
                "runtime": str(slot_b),
                "backend": "zapret",
            }
        except Exception as error:
            self._log("error", "Orchestrator apply_plan failed", error=str(error))
            try:
                self._full_rollback(baseline)
            except Exception:
                pass
            return {
                "ok": False,
                "applied": [],
                "skipped": applied,
                "results": [],
                "restarted": False,
                "error": str(error),
                "rolled_back": True,
                "backend": "zapret",
            }

    def _apply_plan_zapret2(
        self,
        steps: list[TunerStep] | list[dict[str, Any]] | None,
        *,
        probe_targets: list[dict[str, str]] | None = None,
        required_hosts: list[str] | None = None,
        restart: bool | None = None,
    ) -> dict[str, Any]:
        """Zapret2: hostlist/ipset edits reload without restart; strategy change restarts once."""
        from zapret_hub.services.orchestrator import zapret2_hub

        normalized = self._normalize_steps(steps)
        normalized = self._coalesce_list_steps(normalized)
        if not normalized:
            return {"ok": True, "applied": [], "skipped": [], "results": [], "restarted": False, "backend": "zapret2"}

        was_running = self._zapret2_running() if restart is None else bool(restart)
        baseline = self.snapshot()
        applied: list[dict[str, Any]] = []
        needs_restart = False
        try:
            for step in normalized:
                changed = self._apply_one_mutation(step, backend="zapret2")
                applied.append({"kind": step.kind, "value": step.value, "reason": step.reason})
                # Hostlist/ipset edits reload without restart (bol-van docs).
                # Only Lua strategy rewrite needs winws2 restart.
                if changed == "restart":
                    needs_restart = True

            # List-only changes: bol-van docs — files reload automatically, no restart.
            if was_running and needs_restart:
                # Soft-kill then restart — avoid deleting runtime between stop and start.
                try:
                    if hasattr(self.context.processes, "_soft_stop_zapret2_image"):
                        self.context.processes._soft_stop_zapret2_image()
                    else:
                        self.context.processes.stop_component("zapret2")
                except Exception as error:
                    self._log("warning", "Zapret2 stop before strategy restart failed", error=str(error))
                state = self.context.processes.start_component("zapret2")
                if str(getattr(state, "status", "")) != "running":
                    self._full_rollback_zapret2(baseline)
                    return {
                        "ok": False,
                        "applied": [],
                        "skipped": applied,
                        "results": [],
                        "restarted": False,
                        "rolled_back": True,
                        "error": str(getattr(state, "last_error", "") or "zapret2_restart_failed"),
                        "backend": "zapret2",
                    }
                time.sleep(self._settle_s)
            elif not was_running and needs_restart:
                # Offline strategy change is just settings; start not required here.
                pass

            targets = list(probe_targets or [])
            ok = True
            if targets and (was_running or needs_restart):
                # Brief pause so hostlist mtime reload can pick up new domains.
                time.sleep(0.35)
                results = self._probe(targets)
                ok = probe_required_ok(results, required_hosts=required_hosts or [])
            if not ok:
                self._log("info", "Zapret2 plan failed probe — rollback")
                self._full_rollback_zapret2(baseline)
                return {
                    "ok": False,
                    "applied": [],
                    "skipped": applied,
                    "results": [],
                    "restarted": bool(needs_restart and was_running),
                    "rolled_back": True,
                    "error": "probe_failed",
                    "backend": "zapret2",
                }

            self.snapshot()
            return {
                "ok": True,
                "applied": applied,
                "skipped": [],
                "results": [{"ok": True, "restarted": bool(needs_restart and was_running)}],
                "restarted": bool(needs_restart and was_running),
                "backend": "zapret2",
                "listsDir": str(zapret2_hub.zapret2_lists_dir(Path(self.context.paths.configs_dir))),
            }
        except Exception as error:
            self._log("error", "Zapret2 apply_plan failed", error=str(error))
            try:
                self._full_rollback_zapret2(baseline)
            except Exception:
                pass
            return {
                "ok": False,
                "applied": [],
                "skipped": applied,
                "results": [],
                "restarted": False,
                "error": str(error),
                "rolled_back": True,
                "backend": "zapret2",
            }

    def _full_rollback_zapret2(self, baseline: dict[str, Any] | None = None) -> bool:
        good = dict(baseline or self.load_last_good() or {})
        if not good:
            return False
        changes: dict[str, Any] = {}
        for key in _SETTINGS_KEYS:
            if key in good and good[key] is not None:
                changes[key] = good[key]
        if changes:
            try:
                self.context.settings.update(**changes)
            except Exception as error:
                self._log("warning", "Zapret2 rollback settings failed", error=str(error))
        try:
            if self._zapret2_running():
                self.context.processes.stop_component("zapret2")
            state = self.context.processes.start_component("zapret2")
            ok = str(getattr(state, "status", "")) == "running"
            if ok:
                self.last_good = dict(good)
            return ok
        except Exception:
            return False

    def _zapret2_running(self) -> bool:
        try:
            states = {item.component_id: item for item in self.context.processes.list_states()}
            state = states.get("zapret2")
            return bool(state and getattr(state, "status", "") == "running")
        except Exception:
            return False

    def apply_knobs(self, steps: list[Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self.apply_plan(steps, **kwargs)

    def apply(self, steps: list[Any] | None = None, **kwargs: Any) -> bool:
        return bool(self.apply_plan(steps, **kwargs).get("ok"))

    def apply_step(
        self,
        step: TunerStep,
        *,
        probe_targets: list[dict[str, str]] | None = None,
        required_hosts: list[str] | None = None,
        was_running: bool | None = None,
    ) -> dict[str, Any]:
        """Legacy single-step API — delegates to batched apply_plan."""
        return self.apply_plan(
            [step],
            probe_targets=probe_targets,
            required_hosts=required_hosts,
            restart=was_running,
        )

    def _full_rollback(self, baseline: dict[str, Any] | None = None) -> bool:
        """Restore settings AND runtime from baseline / last_good. Always together."""
        good = dict(baseline or self.load_last_good() or {})
        if not good:
            return self._rebuild_and_maybe_restart(restart=True)

        changes: dict[str, Any] = {}
        for key in _SETTINGS_KEYS:
            if key in good and good[key] is not None:
                changes[key] = good[key]
        # Restore mod enables explicitly (ids list + ModsManager flags).
        enabled_mods = list(good.get("enabled_mod_ids") or [])
        enabled_mods2 = list(good.get("enabled_zapret2_mod_ids") or [])
        if changes:
            try:
                self.context.settings.update(**changes)
            except Exception as error:
                self._log("warning", "Rollback settings update failed", error=str(error))
        self._restore_mod_enables(enabled_mods)
        self._restore_mod2_enables(enabled_mods2)

        runtime_path = str(good.get("runtime_path") or "")
        path_ok = bool(runtime_path and Path(runtime_path).exists())
        try:
            if self._zapret_running():
                self.context.processes.stop_component("zapret")
        except Exception:
            pass

        if path_ok:
            try:
                self.context.processes.pin_orchestrator_runtime(Path(runtime_path))
            except Exception:
                pass
            state = self.context.processes.start_zapret_from_runtime(Path(runtime_path))
            try:
                self.context.processes.pin_orchestrator_runtime(None)
            except Exception:
                pass
            if str(getattr(state, "status", "")) == "running":
                self.last_good = dict(good)
                return True
            self._log("warning", "Rollback start from saved path failed — full rebuild")

        ok = self._rebuild_and_maybe_restart(restart=True)
        if ok:
            self.snapshot()
        return ok

    def rollback(self, *, restart: bool = True) -> bool:
        if not restart:
            good = self.load_last_good()
            if not good:
                return False
            changes = {k: good[k] for k in _SETTINGS_KEYS if k in good and good[k] is not None}
            if changes:
                self.context.settings.update(**changes)
            self._restore_mod_enables(list(good.get("enabled_mod_ids") or []))
            self._restore_mod2_enables(list(good.get("enabled_zapret2_mod_ids") or []))
            return True
        return self._full_rollback()

    def _restore_mod_enables(self, enabled_ids: list[str]) -> None:
        mods = getattr(self.context, "mods", None)
        if mods is None:
            return
        want = {str(item) for item in enabled_ids}
        try:
            installed = mods.list_installed()
        except Exception:
            return
        for mod in installed:
            should = mod.id in want
            if bool(mod.enabled) == should:
                continue
            try:
                mods.set_enabled(mod.id, should)
            except Exception as error:
                self._log("warning", "Rollback mod enable failed", mod_id=mod.id, error=str(error))

    def _restore_mod2_enables(self, enabled_ids: list[str]) -> None:
        mods2 = getattr(self.context, "mods2", None)
        if mods2 is None:
            return
        want = {str(item) for item in enabled_ids}
        try:
            installed = mods2.list_installed()
        except Exception:
            return
        for mod in installed:
            should = mod.id in want
            if bool(mod.enabled) == should:
                continue
            try:
                mods2.set_enabled(mod.id, should)
            except Exception as error:
                self._log("warning", "Rollback Zapret2 mod enable failed", mod_id=mod.id, error=str(error))

    def commit_trusted_general(self, general_id: str, *, snapshot_after: bool = False) -> None:
        if not general_id:
            return
        self.context.settings.update(
            trusted_general=general_id,
            selected_zapret_general=general_id,
            general_autotest_done=True,
        )
        if self.knowledge is not None:
            try:
                self.knowledge.rank_general(general_id, 5.0)
            except Exception:
                pass
        if snapshot_after:
            self.snapshot()

    def apply_and_start_trusted(
        self,
        *,
        general_id: str,
        probe_targets: list[dict[str, str]],
        required_hosts: list[str],
    ) -> dict[str, Any]:
        """Bootstrap: mutate to trusted general, stage/start, probe; rollback to pre-bootstrap on fail."""
        baseline = self.snapshot()  # BEFORE trusted mutation
        live_a = getattr(self.context.processes, "_current_zapret_runtime", None)
        if live_a is not None:
            try:
                self.context.processes.pin_orchestrator_runtime(Path(live_a))
            except Exception:
                pass

        try:
            self.commit_trusted_general(general_id, snapshot_after=False)
            self._rebuild_snapshot_only()
            slot_b = self._stage_candidate_b()
            if hasattr(self.context.processes, "hot_replace_zapret_runtime"):
                state = self.context.processes.hot_replace_zapret_runtime(slot_b)
            else:
                try:
                    if self._zapret_running():
                        self.context.processes.stop_component("zapret")
                except Exception:
                    pass
                state = self.context.processes.start_zapret_from_runtime(slot_b)
            if str(getattr(state, "status", "")) != "running":
                self._full_rollback(baseline)
                return {"ok": False, "error": str(getattr(state, "last_error", "") or "start_failed")}
            time.sleep(self._settle_s)
            results = self._probe(probe_targets)
            ok = probe_required_ok(results, required_hosts=required_hosts)
            if not ok:
                self._full_rollback(baseline)
                return {"ok": False, "error": "probe_failed", "results": [r.__dict__ for r in results]}
            try:
                self.context.processes.pin_orchestrator_runtime(None)
            except Exception:
                pass
            self.snapshot(force_runtime=slot_b)
            return {"ok": True, "runtime": str(slot_b), "general": general_id}
        except Exception as error:
            try:
                self._full_rollback(baseline)
            except Exception:
                pass
            return {"ok": False, "error": str(error)}

    def _normalize_steps(self, steps: list[Any] | None) -> list[TunerStep]:
        out: list[TunerStep] = []
        seen: set[tuple[str, str]] = set()
        for raw in steps or []:
            if isinstance(raw, TunerStep):
                step = raw
            else:
                step = TunerStep(
                    kind=str(raw.get("kind") or ""),
                    value=str(raw.get("value") or ""),
                    reason=str(raw.get("reason") or ""),
                    label_ru=str(raw.get("label_ru") or ""),
                    label_en=str(raw.get("label_en") or ""),
                )
            if not step.kind or not step.value:
                continue
            key = (step.kind, step.value)
            if key in seen:
                continue
            seen.add(key)
            out.append(step)
        return out

    def _apply_one_mutation(self, step: TunerStep, *, backend: str = "zapret") -> str:
        if step.kind in {"add_domain", "add_ip", "exclude_domain"}:
            self._apply_list_step(step, backend=backend)
            return "lists"
        if step.kind == "enable_mod":
            if backend == "zapret2":
                self._log("info", "Skipping enable_mod on zapret2 backend", mod_id=step.value)
                return "skip"
            self._apply_enable_mod(step.value)
            return "mods"
        return self._apply_settings_step(step, backend=backend)

    def _apply_list_step(self, step: TunerStep, *, backend: str = "zapret") -> list[str]:
        values = [part.strip() for part in str(step.value or "").replace(",", "\n").splitlines() if part.strip()]
        if not values:
            return []
        if backend == "zapret2":
            from zapret_hub.services.orchestrator import zapret2_hub

            configs = Path(self.context.paths.configs_dir)
            if step.kind == "add_domain":
                return zapret2_hub.add_domains(configs, values)
            if step.kind == "exclude_domain":
                return zapret2_hub.exclude_domains(configs, values)
            if step.kind == "add_ip":
                return zapret2_hub.add_ips(configs, values)
            return []

        configs = Path(self.context.paths.configs_dir)
        learner = HostlistLearner(configs)
        if step.kind == "add_domain":
            return learner.add_domains(values)
        if step.kind == "exclude_domain":
            return learner.exclude_domains(values)
        if step.kind == "add_ip":
            return learner.add_ips(values)
        return []

    def _coalesce_list_steps(self, steps: list[TunerStep]) -> list[TunerStep]:
        """Merge many add_domain/add_ip/exclude into one write each."""
        domains: list[str] = []
        ips: list[str] = []
        excludes: list[str] = []
        other: list[TunerStep] = []
        meta: dict[str, TunerStep] = {}
        for step in steps:
            if step.kind == "add_domain":
                domains.extend(
                    part.strip() for part in str(step.value or "").replace(",", "\n").splitlines() if part.strip()
                )
                meta["add_domain"] = step
            elif step.kind == "add_ip":
                ips.extend(
                    part.strip() for part in str(step.value or "").replace(",", "\n").splitlines() if part.strip()
                )
                meta["add_ip"] = step
            elif step.kind == "exclude_domain":
                excludes.extend(
                    part.strip() for part in str(step.value or "").replace(",", "\n").splitlines() if part.strip()
                )
                meta["exclude_domain"] = step
            else:
                other.append(step)

        def uniq(items: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for item in items:
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
            return out

        merged: list[TunerStep] = []
        domains = uniq(domains)
        ips = uniq(ips)
        excludes = uniq(excludes)
        if domains:
            base = meta.get("add_domain")
            preview = domains[0] if len(domains) == 1 else f"{len(domains)} доменов"
            merged.append(
                TunerStep(
                    kind="add_domain",
                    value="\n".join(domains),
                    reason=str(getattr(base, "reason", "") or "external_miss"),
                    label_ru=f"Добавляю {preview} в списки",
                    label_en=f"Adding {preview} to lists",
                )
            )
        if ips:
            base = meta.get("add_ip")
            preview = ips[0] if len(ips) == 1 else f"{len(ips)} адресов"
            merged.append(
                TunerStep(
                    kind="add_ip",
                    value="\n".join(ips),
                    reason=str(getattr(base, "reason", "") or "external_miss"),
                    label_ru=f"Добавляю {preview}",
                    label_en=f"Adding {preview}",
                )
            )
        if excludes:
            base = meta.get("exclude_domain")
            preview = excludes[0] if len(excludes) == 1 else f"{len(excludes)} доменов"
            merged.append(
                TunerStep(
                    kind="exclude_domain",
                    value="\n".join(excludes),
                    reason=str(getattr(base, "reason", "") or "over_block"),
                    label_ru=f"Исключаю {preview}",
                    label_en=f"Excluding {preview}",
                )
            )
        return merged + other

    def _apply_enable_mod(self, mod_id: str) -> None:
        mods = getattr(self.context, "mods", None)
        if mods is None:
            raise RuntimeError("Mods manager unavailable")
        installed_ids = {item.id for item in mods.list_installed()}
        if mod_id not in installed_ids:
            try:
                index_ids = {item.id for item in mods.fetch_index()}
            except Exception:
                index_ids = set()
            if mod_id in index_ids:
                mods.install(mod_id)
            else:
                raise RuntimeError(f"Mod not installed: {mod_id}")
        mods.set_enabled(mod_id, True)
        self._log("info", "Orchestrator enabled mod", mod_id=mod_id)

    def _stage_candidate_b(self) -> Path:
        processes = self.context.processes
        if hasattr(processes, "stage_zapret_candidate_runtime"):
            return Path(processes.stage_zapret_candidate_runtime())
        self._rebuild_snapshot_only()
        live = getattr(processes, "_current_zapret_runtime", None)
        if live is None:
            raise RuntimeError("Failed to stage candidate runtime")
        return Path(live)

    def _apply_settings_step(self, step: TunerStep, *, backend: str = "zapret") -> str:
        from zapret_hub.services.orchestrator import zapret2_hub

        settings = self.context.settings.get()
        configs = Path(self.context.paths.configs_dir)

        if step.kind == "enable_service":
            selected = {str(item) for item in (settings.selected_service_ids or [])}
            if step.value in SERVICE_PRESET_IDS:
                selected.add(step.value)
            ordered = [preset.id for preset in SERVICE_PRESETS if preset.id in selected]
            changes: dict[str, Any] = {"selected_service_ids": ordered}
            enabled = {str(item) for item in (settings.enabled_component_ids or [])}
            if backend == "zapret2":
                enabled.add("zapret2")
                enabled.discard("zapret")
            elif step.value not in {"telegram-desktop", "ai"}:
                enabled.add("zapret")
            if step.value == "telegram-desktop":
                enabled.add("tg-ws-proxy")
            if step.value == "ai":
                enabled.add("xbox-dns")
            if step.value == "gaming":
                changes["zapret_game_filter_mode"] = "tcpudp"
            if step.value == "fortnite":
                changes["zapret_ipset_mode"] = "any"
                changes["zapret_game_filter_mode"] = "tcpudp"
            changes["enabled_component_ids"] = sorted(enabled)
            self.context.settings.update(**changes)
            # One-shot: dump all known domains/IPs for this service into the active backend lists.
            harvested_domains = zapret2_hub.harvest_service_domains([step.value])
            harvested_ips = zapret2_hub.harvest_service_ips([step.value])
            if backend == "zapret2":
                zapret2_hub.seed_service_lists(configs, [step.value])
            else:
                learner = HostlistLearner(configs)
                if harvested_domains:
                    learner.add_domains(harvested_domains)
                if harvested_ips:
                    learner.add_ips(harvested_ips)
            return "lists"

        if step.kind == "ipset":
            if backend == "zapret2":
                # Widen coverage by seeding Google/Discord nets; no classic ipset mode on z2.
                zapret2_hub.add_ips(configs, list(zapret2_hub.BYPASS_SEED_NETWORKS))
                return "lists"
            self.context.settings.update(zapret_ipset_mode=step.value)
            return "settings"

        if step.kind == "game_filter":
            if backend == "zapret2":
                return "skip"
            self.context.settings.update(zapret_game_filter_mode=step.value)
            return "settings"

        if step.kind == "gaming_set":
            if backend == "zapret2":
                return "skip"
            self.context.settings.update(zapret_gaming_set=step.value)
            return "settings"

        if step.kind == "general":
            if backend == "zapret2":
                strategy_id = step.value if step.value in zapret2_hub.STRATEGY_IDS else zapret2_hub.next_strategy_id(
                    str(getattr(settings, "zapret2_strategy_id", "balanced") or "balanced")
                )
                # Accept either strategy id or "zapret2|balanced" style.
                if "|" in strategy_id:
                    strategy_id = strategy_id.rsplit("|", 1)[-1]
                if strategy_id not in zapret2_hub.STRATEGY_IDS:
                    strategy_id = "balanced"
                self.context.settings.update(zapret2_strategy_id=strategy_id)
                zapret2_hub.write_hub_strategy_lua(configs, strategy_id)
                return "restart"
            self.context.settings.update(selected_zapret_general=step.value)
            return "settings"

        return "skip"

    def _rebuild_snapshot_only(self) -> None:
        try:
            self.context.merge.rebuild()
        except Exception as error:
            self._log("warning", "merge.rebuild failed", error=str(error))
        try:
            self.context.files._invalidate_collection_cache()
            self.context.files.rebuild_materialized_collections()
        except Exception:
            pass
        try:
            self.context.processes.rebuild_zapret_runtime_snapshot()
        except Exception:
            pass

    def _rebuild_and_maybe_restart(self, *, restart: bool) -> bool:
        self._rebuild_snapshot_only()
        if not restart:
            return False
        try:
            if self._zapret_running():
                self.context.processes.stop_component("zapret")
            state = self.context.processes.start_component("zapret")
            return bool(getattr(state, "status", "") == "running")
        except Exception:
            return False

    def _zapret_running(self) -> bool:
        try:
            states = {item.component_id: item for item in self.context.processes.list_states()}
            state = states.get("zapret")
            return bool(state and getattr(state, "status", "") == "running")
        except Exception:
            return False

    def _probe(self, targets: list[dict[str, str]]) -> list[ProbeResult]:
        normalized: list[dict[str, str]] = []
        for item in targets:
            value = str(item.get("value") or item.get("url") or item.get("host") or "").strip()
            if not value:
                continue
            normalized.append({"value": value})
        if not normalized:
            return []
        return self.signals.probe_targets(normalized, timeout_s=4.0, require_http=True)

    def probe_for_services(self, service_ids: list[str]) -> list[dict[str, str]]:
        targets: list[dict[str, str]] = []
        seen: set[str] = set()
        for service_id in service_ids:
            rule = SERVICE_RULES.get(service_id)
            if rule is None:
                continue
            for _name, value in rule.test_targets:
                key = value.strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                targets.append({"value": value})
        return targets
