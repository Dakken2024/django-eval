import logging
import threading
import time
from typing import Optional

from .cache_keys import CacheKeys
from .cache import get_cache
from .settings import EvalEngineSettings
from .compiled_rule_engine import RuleRegistry

logger = logging.getLogger(__name__)


class RegistryWatcher:
    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._started = False
                    cls._instance._local_version = -1
                    cls._instance._thread = None
                    cls._instance._stop_event = threading.Event()
                    cls._instance._cache = get_cache()
        return cls._instance

    @property
    def is_running(self) -> bool:
        return self._started and self._thread is not None and self._thread.is_alive()

    def start(self, interval: int = None):
        if self._started:
            logger.debug("RegistryWatcher already started")
            return

        if not EvalEngineSettings.registry_watcher_enabled():
            logger.info("RegistryWatcher disabled by settings")
            return

        interval = interval or EvalEngineSettings.registry_watcher_interval()
        self._started = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop,
            args=(interval,),
            daemon=True,
            name="rule-registry-watcher"
        )
        self._thread.start()
        logger.info(f"RegistryWatcher started (interval={interval}s)")

    def stop(self):
        if not self._started:
            return
        self._stop_event.set()
        self._started = False
        logger.info("RegistryWatcher stopped")

    def _watch_loop(self, interval: int):
        consecutive_errors = 0
        max_consecutive_errors = EvalEngineSettings.get('REGISTRY_WATCHER_MAX_ERRORS', 10)

        while not self._stop_event.is_set():
            try:
                self._check_version()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"RegistryWatcher error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical("RegistryWatcher: too many consecutive errors, entering backoff")
                    backoff = min(interval * 10, 60)
                    self._stop_event.wait(backoff)
                    consecutive_errors = 0

            self._stop_event.wait(interval)

    def _check_version(self):
        try:
            remote_version = self._cache.get(CacheKeys.RULE_REGISTRY_VERSION)
        except Exception:
            remote_version = None

        if remote_version is None:
            return

        if self._local_version == -1:
            self._local_version = remote_version
            return

        if remote_version != self._local_version:
            logger.info(f"Rule version changed: {self._local_version} -> {remote_version}")
            self._incremental_reload()
            self._local_version = remote_version

    def _incremental_reload(self):
        try:
            from .models import RuleConfig
        except Exception as e:
            logger.error(f"RegistryWatcher: failed to import RuleConfig: {e}")
            return

        registry = RuleRegistry()
        try:
            active_rules = RuleConfig.objects.filter(is_active=True)
        except Exception as e:
            logger.error(f"RegistryWatcher: failed to query RuleConfig: {e}")
            return

        active_ids = set()
        for rule in active_rules:
            active_ids.add(rule.rule_id)
            local_ver = registry._versions.get(rule.rule_id, -1)
            if rule.version != local_ver:
                try:
                    compiled = registry._compile_rule(rule)
                    if compiled is not None:
                        registry.register(rule.rule_id, compiled, version=rule.version)
                        logger.info(f"RegistryWatcher: recompiled rule {rule.rule_id} v{rule.version}")
                except Exception as e:
                    logger.error(f"RegistryWatcher: failed to compile {rule.rule_id}: {e}")

        with registry._lock:
            stale_ids = [rid for rid in registry._tables if rid not in active_ids]
            for rid in stale_ids:
                registry._tables.pop(rid, None)
                registry._versions.pop(rid, None)
                logger.info(f"RegistryWatcher: removed stale rule {rid}")

    @classmethod
    def bump_version(cls):
        try:
            cache = get_cache()
            current = cache.get(CacheKeys.RULE_REGISTRY_VERSION, 0)
            cache.set(CacheKeys.RULE_REGISTRY_VERSION, current + 1, timeout=None)
        except Exception as e:
            logger.error(f"RegistryWatcher: failed to bump version: {e}")