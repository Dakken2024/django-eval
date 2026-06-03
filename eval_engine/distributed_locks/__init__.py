"""
Distributed Locks Module for django-eval

Provides distributed locking mechanisms for multi-instance deployments.
Supports Redis and Zookeeper backends.
"""

from .lock_backend import DistributedLock, LockBackend
from .redis_backend import RedisLockBackend
from .zookeeper_backend import ZookeeperLockBackend

__all__ = [
    'DistributedLock',
    'LockBackend', 
    'RedisLockBackend',
    'ZookeeperLockBackend',
]
