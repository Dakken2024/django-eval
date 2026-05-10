"""Pluggable cache backend for django-eval.

Supports Django cache framework, Redis, in-memory, and dummy (no-op) backends.
Backend is selected via EVAL_ENGINE_CACHE_BACKEND setting.

Usage:
    from eval_engine.cache import get_cache
    cache = get_cache()
    cache.set('key', value, timeout=300)
    value = cache.get('key')
"""

import logging
import threading
import time
from typing import Any, Optional

from django.conf import settings
from .settings import EvalEngineSettings

logger = logging.getLogger(__name__)


class BaseCacheBackend:
    """Abstract base class for cache backends."""

    def get(self, key: str, default=None):
        raise NotImplementedError

    def set(self, key: str, value: Any, timeout: Optional[int] = None):
        raise NotImplementedError

    def delete(self, key: str):
        raise NotImplementedError

    def clear(self):
        raise NotImplementedError

    def get_many(self, keys: list):
        return {k: self.get(k) for k in keys}

    def set_many(self, mapping: dict, timeout: Optional[int] = None):
        for k, v in mapping.items():
            self.set(k, v, timeout)


class DjangoCacheBackend(BaseCacheBackend):
    """Uses Django's configured cache framework (default)."""

    def __init__(self):
        from django.core.cache import cache
        self._cache = cache

    def get(self, key: str, default=None):
        try:
            return self._cache.get(key, default)
        except Exception as e:
            logger.warning(f"Django cache get failed for key {key}: {e}")
            return default

    def set(self, key: str, value: Any, timeout: Optional[int] = None):
        try:
            self._cache.set(key, value, timeout=timeout)
        except Exception as e:
            logger.warning(f"Django cache set failed for key {key}: {e}")

    def delete(self, key: str):
        try:
            self._cache.delete(key)
        except Exception as e:
            logger.warning(f"Django cache delete failed for key {key}: {e}")

    def clear(self):
        try:
            self._cache.clear()
        except Exception as e:
            logger.warning(f"Django cache clear failed: {e}")


class MemoryCacheBackend(BaseCacheBackend):
    """Thread-safe in-memory cache. Falls back when no external cache is available."""

    def __init__(self):
        self._store = {}
        self._expires = {}
        self._lock = threading.RLock()

    def get(self, key: str, default=None):
        with self._lock:
            if key in self._expires and time.time() > self._expires[key]:
                self._store.pop(key, None)
                self._expires.pop(key, None)
                return default
            return self._store.get(key, default)

    def set(self, key: str, value: Any, timeout: Optional[int] = None):
        with self._lock:
            self._store[key] = value
            if timeout is not None:
                self._expires[key] = time.time() + timeout
            else:
                self._expires.pop(key, None)

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)
            self._expires.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()
            self._expires.clear()


class RedisCacheBackend(BaseCacheBackend):
    """Direct Redis backend (optional, requires redis package)."""

    def __init__(self, url: Optional[str] = None):
        try:
            import redis
        except ImportError:
            raise ImportError(
                "Redis cache backend requires 'redis' package. "
                "Install with: pip install django-eval[redis]"
            )

        redis_url = url or getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        self._client = redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str, default=None):
        try:
            value = self._client.get(key)
            if value is None:
                return default
            import json
            return json.loads(value)
        except Exception as e:
            logger.warning(f"Redis cache get failed for key {key}: {e}")
            return default

    def set(self, key: str, value: Any, timeout: Optional[int] = None):
        try:
            import json
            serialized = json.dumps(value)
            if timeout:
                self._client.setex(key, timeout, serialized)
            else:
                self._client.set(key, serialized)
        except Exception as e:
            logger.warning(f"Redis cache set failed for key {key}: {e}")

    def delete(self, key: str):
        try:
            self._client.delete(key)
        except Exception as e:
            logger.warning(f"Redis cache delete failed for key {key}: {e}")

    def clear(self):
        try:
            self._client.flushdb()
        except Exception as e:
            logger.warning(f"Redis cache clear failed: {e}")


class DummyCacheBackend(BaseCacheBackend):
    """No-op cache backend for testing or when caching is disabled."""

    def get(self, key: str, default=None):
        return default

    def set(self, key: str, value: Any, timeout: Optional[int] = None):
        pass

    def delete(self, key: str):
        pass

    def clear(self):
        pass


# Registry of available backends
_BACKENDS = {
    'django': DjangoCacheBackend,
    'memory': MemoryCacheBackend,
    'redis': RedisCacheBackend,
    'dummy': DummyCacheBackend,
}

# Singleton instance
_cache_instance = None
_cache_lock = threading.Lock()


def get_cache() -> BaseCacheBackend:
    """Get the configured cache backend instance (singleton)."""
    global _cache_instance

    if _cache_instance is not None:
        return _cache_instance

    with _cache_lock:
        if _cache_instance is not None:
            return _cache_instance

        backend_name = EvalEngineSettings.get('CACHE_BACKEND', 'django')
        enabled = EvalEngineSettings.cache_enabled()

        if not enabled:
            _cache_instance = DummyCacheBackend()
            logger.info("Cache disabled, using DummyCacheBackend")
            return _cache_instance

        backend_cls = _BACKENDS.get(backend_name)
        if backend_cls is None:
            logger.warning(
                f"Unknown cache backend '{backend_name}', falling back to DjangoCacheBackend"
            )
            backend_cls = DjangoCacheBackend

        try:
            _cache_instance = backend_cls()
            logger.info(f"Cache backend initialized: {backend_cls.__name__}")
        except Exception as e:
            logger.error(
                f"Failed to initialize {backend_cls.__name__}: {e}. "
                "Falling back to MemoryCacheBackend."
            )
            _cache_instance = MemoryCacheBackend()

        return _cache_instance


def reset_cache():
    """Reset the cache singleton (useful for testing)."""
    global _cache_instance
    with _cache_lock:
        _cache_instance = None