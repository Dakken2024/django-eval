"""
Redis-based Distributed Lock Backend

Implementation using Redis SETNX for distributed locking.
Requires redis-py library.
"""

import time
import uuid
from typing import Optional
from .lock_backend import LockBackend, LockInfo


class RedisLockBackend(LockBackend):
    """
    Redis-based distributed lock implementation.
    
    Uses Redis SETNX command with TTL for atomic lock acquisition.
    Supports lock extension and automatic expiry.
    
    Usage:
        from django.core.cache import cache
        
        backend = RedisLockBackend(cache)
        with DistributedLock(backend, 'rule_123') as lock:
            if lock.acquired:
                # Safe to modify
                pass
    """
    
    def __init__(self, redis_client, key_prefix: str = "django_eval:lock:"):
        """
        Initialize Redis lock backend.
        
        Args:
            redis_client: Redis client instance (django-redis or redis-py)
            key_prefix: Prefix for lock keys
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    def _make_key(self, resource: str) -> str:
        """Generate Redis key for a resource."""
        return f"{self.key_prefix}{resource}"
    
    def acquire(
        self,
        resource: str,
        timeout_ms: int = 5000,
        ttl_ms: int = 30000
    ) -> Optional[str]:
        """Acquire lock using Redis SETNX with timeout."""
        key = self._make_key(resource)
        token = str(uuid.uuid4())
        ttl_sec = ttl_ms / 1000.0
        
        start_time = time.time()
        timeout_sec = timeout_ms / 1000.0
        
        while True:
            # Try to set key only if not exists (atomic operation)
            acquired = self.redis.set(
                key,
                token,
                nx=True,
                ex=ttl_sec
            )
            
            if acquired:
                return token
            
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout_sec:
                return None
            
            # Wait briefly before retrying (with jitter)
            import random
            sleep_time = min(0.05 + random.random() * 0.05, timeout_sec - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def release(self, resource: str, token: str) -> bool:
        """
        Release lock only if we own it.
        
        Uses Lua script for atomic check-and-delete.
        """
        key = self._make_key(resource)
        
        # Lua script to atomically check owner and delete
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = self.redis.eval(lua_script, 1, key, token)
            return result == 1
        except Exception:
            # Fallback for clients without eval support
            current_value = self.redis.get(key)
            if current_value and current_value.decode('utf-8') == token:
                self.redis.delete(key)
                return True
            return False
    
    def extend(self, resource: str, token: str, ttl_ms: int) -> bool:
        """
        Extend lock TTL only if we own it.
        
        Uses Lua script for atomic check-and-expire.
        """
        key = self._make_key(resource)
        ttl_sec = ttl_ms / 1000.0
        
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        
        try:
            result = self.redis.eval(lua_script, 1, key, token, ttl_sec)
            return result == 1
        except Exception:
            # Fallback
            current_value = self.redis.get(key)
            if current_value and current_value.decode('utf-8') == token:
                return self.redis.expire(key, ttl_sec)
            return False
    
    def is_locked(self, resource: str) -> bool:
        """Check if resource is locked."""
        key = self._make_key(resource)
        return self.redis.exists(key) == 1
    
    def get_lock_info(self, resource: str) -> Optional[LockInfo]:
        """Get lock information (limited in Redis backend)."""
        key = self._make_key(resource)
        
        token = self.redis.get(key)
        if not token:
            return None
        
        # Redis doesn't store creation time, so we provide limited info
        ttl_ms = self.redis.ttl(key) * 1000 if self.redis.ttl(key) > 0 else 0
        
        return LockInfo(
            lock_id=token.decode('utf-8') if isinstance(token, bytes) else token,
            owner="unknown",  # Redis doesn't track owner metadata
            acquired_at=time.time(),  # Approximate
            expires_at=time.time() + (ttl_ms / 1000.0),
            resource=resource
        )
