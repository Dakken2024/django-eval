"""
Distributed Lock Backend Interface

Abstract base classes for distributed lock implementations.
"""

import abc
import time
import uuid
from typing import Optional, ContextManager
from dataclasses import dataclass


@dataclass
class LockInfo:
    """Information about a held lock."""
    lock_id: str
    owner: str
    acquired_at: float
    expires_at: float
    resource: str


class LockBackend(abc.ABC):
    """Abstract base class for distributed lock backends."""
    
    @abc.abstractmethod
    def acquire(
        self, 
        resource: str, 
        timeout_ms: int = 5000,
        ttl_ms: int = 30000
    ) -> Optional[str]:
        """
        Attempt to acquire a lock on the given resource.
        
        Args:
            resource: Unique identifier for the resource to lock
            timeout_ms: Maximum time to wait for acquiring the lock
            ttl_ms: Time-to-live for the lock (auto-release)
            
        Returns:
            Lock token if acquired, None otherwise
        """
        pass
    
    @abc.abstractmethod
    def release(self, resource: str, token: str) -> bool:
        """
        Release a held lock.
        
        Args:
            resource: Resource identifier
            token: Lock token returned by acquire()
            
        Returns:
            True if released successfully, False otherwise
        """
        pass
    
    @abc.abstractmethod
    def extend(self, resource: str, token: str, ttl_ms: int) -> bool:
        """
        Extend the TTL of a held lock.
        
        Args:
            resource: Resource identifier
            token: Lock token
            ttl_ms: New TTL in milliseconds
            
        Returns:
            True if extended successfully, False otherwise
        """
        pass
    
    @abc.abstractmethod
    def is_locked(self, resource: str) -> bool:
        """Check if a resource is currently locked."""
        pass
    
    @abc.abstractmethod
    def get_lock_info(self, resource: str) -> Optional[LockInfo]:
        """Get information about a held lock."""
        pass


class DistributedLock(ContextManager):
    """
    Context manager for distributed locks.
    
    Usage:
        with DistributedLock(backend, 'rule_update_123') as lock:
            if lock.acquired:
                # Safe to modify rule
                update_rule(rule_id)
            else:
                # Another instance is handling this
                log.info("Lock not acquired, skipping")
    """
    
    def __init__(
        self,
        backend: LockBackend,
        resource: str,
        timeout_ms: int = 5000,
        ttl_ms: int = 30000,
        auto_extend: bool = False,
        extend_interval_ms: int = 10000
    ):
        self.backend = backend
        self.resource = resource
        self.timeout_ms = timeout_ms
        self.ttl_ms = ttl_ms
        self.auto_extend = auto_extend
        self.extend_interval_ms = extend_interval_ms
        
        self.token: Optional[str] = None
        self.acquired: bool = False
        self._extend_thread: Optional[threading.Thread] = None
        self._stop_extend = threading.Event()
    
    def __enter__(self) -> 'DistributedLock':
        self.token = self.backend.acquire(
            self.resource,
            timeout_ms=self.timeout_ms,
            ttl_ms=self.ttl_ms
        )
        self.acquired = self.token is not None
        
        if self.acquired and self.auto_extend:
            self._start_auto_extend()
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.auto_extend:
            self._stop_auto_extend()
        
        if self.acquired and self.token:
            self.backend.release(self.resource, self.token)
    
    def _start_auto_extend(self) -> None:
        """Start background thread to auto-extend lock."""
        import threading
        
        self._stop_extend.clear()
        self._extend_thread = threading.Thread(
            target=self._auto_extend_loop,
            daemon=True
        )
        self._extend_thread.start()
    
    def _stop_auto_extend(self) -> None:
        """Stop the auto-extend thread."""
        if self._extend_thread:
            self._stop_extend.set()
            self._extend_thread.join(timeout=1.0)
            self._extend_thread = None
    
    def _auto_extend_loop(self) -> None:
        """Background loop to extend lock before expiry."""
        import time
        
        # Extend at half the TTL to ensure safety margin
        extend_interval_sec = self.extend_interval_ms / 1000.0
        
        while not self._stop_extend.wait(timeout=extend_interval_sec):
            if self.token:
                self.backend.extend(self.resource, self.token, self.ttl_ms)
            else:
                break
    
    def refresh(self) -> bool:
        """Manually refresh the lock TTL."""
        if not self.acquired or not self.token:
            return False
        return self.backend.extend(self.resource, self.token, self.ttl_ms)
