"""
Zookeeper-based Distributed Lock Backend

Implementation using Apache Zookeeper for distributed locking.
Requires kazoo library.
"""

import time
from typing import Optional
from .lock_backend import LockBackend, LockInfo


class ZookeeperLockBackend(LockBackend):
    """
    Zookeeper-based distributed lock implementation.
    
    Uses ephemeral sequential nodes for fair, distributed locking.
    Requires kazoo library.
    
    Usage:
        from kazoo.client import KazooClient
        
        zk = KazooClient(hosts='127.0.0.1:2181')
        zk.start()
        
        backend = ZookeeperLockBackend(zk)
        with DistributedLock(backend, 'rule_123') as lock:
            if lock.acquired:
                # Safe to modify
                pass
    """
    
    def __init__(
        self, 
        zk_client, 
        path_prefix: str = "/django_eval/locks/"
    ):
        """
        Initialize Zookeeper lock backend.
        
        Args:
            zk_client: KazooClient instance
            path_prefix: Base path for lock znodes
        """
        self.zk = zk_client
        self.path_prefix = path_prefix
        
        # Ensure base path exists
        self.zk.ensure_path(path_prefix)
    
    def _make_path(self, resource: str) -> str:
        """Generate Zookeeper path for a resource."""
        # Sanitize resource name for znode
        safe_resource = resource.replace('/', '_').replace('\\', '_')
        return f"{self.path_prefix}{safe_resource}"
    
    def acquire(
        self,
        resource: str,
        timeout_ms: int = 5000,
        ttl_ms: int = 30000
    ) -> Optional[str]:
        """
        Acquire lock using Zookeeper ephemeral sequential node.
        
        Note: TTL is not directly supported in ZK locks.
        Lock is released when session ends or explicitly released.
        """
        path = self._make_path(resource)
        
        # Create lock object
        lock = self.zk.Lock(path, identifier=str(time.time()))
        
        # Try to acquire with timeout
        acquired = lock.acquire(timeout=timeout_ms / 1000.0)
        
        if acquired:
            # Store lock reference for later release
            # We use a simple cache here; in production use proper storage
            if not hasattr(self, '_locks'):
                self._locks = {}
            self._locks[path] = lock
            return path
        
        return None
    
    def release(self, resource: str, token: str) -> bool:
        """Release Zookeeper lock."""
        path = token  # token is the path
        
        try:
            if hasattr(self, '_locks') and path in self._locks:
                lock = self._locks[path]
                lock.release()
                del self._locks[path]
                return True
            return False
        except Exception:
            return False
    
    def extend(self, resource: str, token: str, ttl_ms: int) -> bool:
        """
        Extend lock TTL.
        
        Note: Zookeeper locks don't support TTL extension.
        This is a no-op for ZK backend. Lock persists until released.
        
        Returns True to indicate lock is still held.
        """
        # ZK locks are ephemeral - they last until session ends or released
        # Check if we still hold the lock
        return self.is_locked(resource)
    
    def is_locked(self, resource: str) -> bool:
        """Check if resource is locked."""
        path = self._make_path(resource)
        return self.zk.exists(path) is not None
    
    def get_lock_info(self, resource: str) -> Optional[LockInfo]:
        """Get lock information."""
        path = self._make_path(resource)
        
        stat = self.zk.exists(path)
        if not stat:
            return None
        
        # Get lock data (owner identifier)
        data, stat = self.zk.get(path)
        owner = data.decode('utf-8') if data else "unknown"
        
        return LockInfo(
            lock_id=path,
            owner=owner,
            acquired_at=stat.created,
            expires_at=0,  # ZK locks don't expire automatically
            resource=resource
        )
